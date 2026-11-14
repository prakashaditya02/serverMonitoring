import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.mail import send_mail
from django.db.models import Avg, DateTimeField
from django.db.models.expressions import RawSQL
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import ThresholdForm
from .models import Alert, Record, Threshold
from .serializers import AlertSerializer


class MetricsPush(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            metrics = request.data
            rec = Record.objects.create(
                instance_name=metrics['instance_name'],
                cpu=metrics['cpu_usage'],
                disk=metrics['disk_usage'],
                memory=metrics['memory_usage']
            )
            alerts = []
            try:
                threshold = Threshold.objects.get(server_instance=rec.instance_name)

                if rec.cpu > threshold.cpu_threshold:
                    alerts.append(('cpu', rec.cpu))
                if rec.disk > threshold.disk_threshold:
                    alerts.append(('disk', rec.disk))
                if rec.memory > threshold.memory_threshold:
                    alerts.append(('memory', rec.memory))
                for i in alerts:
                    last_alert = Alert.objects.filter(
                        server_instance=rec.instance_name, metric_type=i[0]
                    ).order_by('-trigger_time').first()
                    if (not last_alert) or (
                        (timezone.now() - last_alert.trigger_time) > datetime.timedelta(minutes=2)
                    ):
                        Alert.objects.create(
                            server_instance=rec.instance_name,
                            metric_type=i[0],
                            value=i[1]
                        )
                        subject = f"{i[0]} Alert on {rec.instance_name}"
                        message = f"""Alert triggered on {rec.instance_name}
Threshold exceeded by {i[0]}
Value: {i[1]}
Time: {timezone.now()}"""
                        recipient = threshold.recipients if threshold.recipients else [
                            settings.ALERT_RECIPIENT_EMAIL
                        ]
                        send_mail(
                            subject,
                            message,
                            settings.EMAIL_HOST_USER,
                            recipient,
                            fail_silently=False
                        )
            except Threshold.DoesNotExist:
                pass

            return Response(
                {"status": "OK", "id": rec.id},
                status=status.HTTP_201_CREATED
            )

        except KeyError as e:
            return Response(
                {"status": "error", "message": f"Missing field: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@login_required
def DashboardView(request):
    return render(request, 'monitor_app/dashboard.html')


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def _known_servers():
    return Record.objects.values_list(
        'instance_name', flat=True
    ).distinct().order_by('instance_name')


class ThresholdListView(StaffRequiredMixin, ListView):
    model = Threshold
    template_name = 'monitor_app/threshold_list.html'
    context_object_name = 'thresholds'
    ordering = ['server_instance']


class ThresholdCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Threshold
    form_class = ThresholdForm
    template_name = 'monitor_app/threshold_form.html'
    success_url = reverse_lazy('threshold-list')
    success_message = 'Threshold added for %(server_instance)s.'

    def get_initial(self):
        initial = super().get_initial()
        server_instance = self.request.GET.get('server')
        if server_instance:
            initial['server_instance'] = server_instance
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['known_servers'] = _known_servers()
        context['page_title'] = 'Add threshold'
        return context


class ThresholdUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Threshold
    form_class = ThresholdForm
    template_name = 'monitor_app/threshold_form.html'
    success_url = reverse_lazy('threshold-list')
    success_message = 'Threshold updated for %(server_instance)s.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['known_servers'] = _known_servers()
        context['page_title'] = 'Edit threshold'
        return context


class ThresholdDeleteView(StaffRequiredMixin, DeleteView):
    model = Threshold
    template_name = 'monitor_app/threshold_confirm_delete.html'
    success_url = reverse_lazy('threshold-list')

    def form_valid(self, form):
        messages.success(
            self.request,
            f'Threshold deleted for {self.object.server_instance}.'
        )
        return super().form_valid(form)


RANGE_CONFIG = {
    '6h': (datetime.timedelta(hours=6), 5, '5m'),
    '24h': (datetime.timedelta(hours=24), 15, '15m'),
    '48h': (datetime.timedelta(hours=48), 30, '30m'),
    '7d': (datetime.timedelta(days=7), 120, '2h'),
}

BUCKET_ORIGIN = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
METRIC_KEYS = ('cpu', 'memory', 'disk')


def _to_iso(value):
    return value.astimezone(datetime.timezone.utc).isoformat().replace(
        '+00:00', 'Z'
    )


class MetricsFetch(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        range_key = request.query_params.get('range', '48h')
        if range_key not in RANGE_CONFIG:
            return Response(
                {'detail': 'Invalid range. Use 6h, 24h, 48h, or 7d.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        range_delta, bucket_minutes, bucket_label = RANGE_CONFIG[range_key]
        end_time = timezone.now()
        start_time = end_time - range_delta

        bucket_expression = RawSQL(
            'date_bin(%s::interval, timing, %s::timestamptz)',
            [f'{bucket_minutes} minutes', BUCKET_ORIGIN.isoformat()],
            output_field=DateTimeField()
        )
        rows = list(
            Record.objects.filter(
                timing__gte=start_time, timing__lte=end_time
            )
            .annotate(bucket=bucket_expression)
            .values('instance_name', 'bucket')
            .annotate(
                cpu=Avg('cpu'),
                memory=Avg('memory'),
                disk=Avg('disk')
            )
            .order_by('bucket', 'instance_name')
        )

        if not rows:
            return Response({
                'range': range_key,
                'bucket': bucket_label,
                'timestamps': [],
                'series': []
            })

        bucket_delta = datetime.timedelta(minutes=bucket_minutes)
        bucket_seconds = int(bucket_delta.total_seconds())
        offset_seconds = int((start_time - BUCKET_ORIGIN).total_seconds())
        aligned_start = BUCKET_ORIGIN + datetime.timedelta(
            seconds=(offset_seconds // bucket_seconds) * bucket_seconds
        )

        timestamps = []
        cursor = aligned_start
        while cursor <= end_time:
            timestamps.append(cursor)
            cursor += bucket_delta

        index_by_second = {
            int(timestamp.timestamp()): index
            for index, timestamp in enumerate(timestamps)
        }
        series = {}
        for row in rows:
            instance_name = row['instance_name']
            entry = series.setdefault(
                instance_name,
                {
                    metric: [None] * len(timestamps)
                    for metric in METRIC_KEYS
                }
            )
            index = index_by_second.get(int(row['bucket'].timestamp()))
            if index is None:
                continue
            entry['cpu'][index] = row['cpu']
            entry['memory'][index] = row['memory']
            entry['disk'][index] = row['disk']

        return Response({
            'range': range_key,
            'bucket': bucket_label,
            'timestamps': [_to_iso(timestamp) for timestamp in timestamps],
            'series': [
                {'instance_name': instance_name, **series[instance_name]}
                for instance_name in sorted(series)
            ]
        })


class LatestRecordFetch(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Record.objects.order_by(
            'instance_name', '-timing'
        ).distinct('instance_name')
        thresholds = Threshold.objects.in_bulk(
            field_name='server_instance'
        )
        now = timezone.now()
        stale_after = getattr(settings, 'STALE_AFTER_SECONDS', 45)

        data = []
        for record in queryset:
            age_seconds = max(
                0, int((now - record.timing).total_seconds())
            )
            threshold = thresholds.get(record.instance_name)
            exceeded = []
            if threshold:
                if record.cpu > threshold.cpu_threshold:
                    exceeded.append('cpu')
                if record.memory > threshold.memory_threshold:
                    exceeded.append('memory')
                if record.disk > threshold.disk_threshold:
                    exceeded.append('disk')

            if age_seconds > stale_after:
                server_status = 'offline'
            elif exceeded:
                server_status = 'critical'
            else:
                server_status = 'ok'

            data.append({
                'instance_name': record.instance_name,
                'cpu': record.cpu,
                'memory': record.memory,
                'disk': record.disk,
                'timing': record.timing.isoformat(),
                'age_seconds': age_seconds,
                'status': server_status,
                'exceeded': exceeded,
                'thresholds': {
                    'id': threshold.id,
                    'cpu': threshold.cpu_threshold,
                    'memory': threshold.memory_threshold,
                    'disk': threshold.disk_threshold,
                } if threshold else None,
            })

        return Response(data)


class ActiveAlerts(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Alert.objects.all().order_by('-trigger_time')[:10]
        serializer = AlertSerializer(queryset, many=True)
        return Response(serializer.data)
