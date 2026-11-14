(function () {
    "use strict";

    const root = document.getElementById("dashboard");
    if (!root) {
        return;
    }

    const config = {
        latestUrl: root.dataset.latestUrl,
        timeseriesUrl: root.dataset.timeseriesUrl,
        alertsUrl: root.dataset.alertsUrl,
        thresholdsUrl: root.dataset.thresholdsUrl,
        loginUrl: root.dataset.loginUrl,
        isStaff: root.dataset.isStaff === "true",
    };

    const state = {
        cards: new Map(),
        chart: null,
        chartData: null,
        chartController: null,
        chartRequestId: 0,
        metric: "cpu",
        range: "48h",
    };

    const METRICS = [
        { key: "cpu", label: "CPU" },
        { key: "memory", label: "Memory" },
        { key: "disk", label: "Disk" },
    ];

    const COLORS = [
        "#0d6efd",
        "#dc3545",
        "#198754",
        "#fd7e14",
        "#6f42c1",
        "#20c997",
        "#d63384",
        "#6610f2",
        "#0dcaf0",
        "#ffc107",
        "#6c757d",
        "#495057",
    ];

    const chartTimestampFormatter = new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });

    const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, {
        numeric: "auto",
    });

    let redirecting = false;

    function showError(elementId, message) {
        const element = document.getElementById(elementId);
        if (!element) {
            return;
        }
        element.textContent = message;
        element.classList.remove("d-none");
    }

    function hideError(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            return;
        }
        element.textContent = "";
        element.classList.add("d-none");
    }

    function redirectToLogin() {
        redirecting = true;
        const next = window.location.pathname + window.location.search;
        window.location.assign(
            config.loginUrl + "?next=" + encodeURIComponent(next)
        );
    }

    async function getJSON(url, options) {
        const response = await fetch(url, {
            cache: "no-store",
            headers: { Accept: "application/json" },
            ...options,
        });

        if (response.status === 401 || response.status === 403) {
            redirectToLogin();
            throw new Error("Not authenticated");
        }

        if (!response.ok) {
            throw new Error("Request failed: " + response.status);
        }

        return response.json();
    }

    function formatNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(1) : "N/A";
    }

    function formatAge(seconds) {
        const value = Number(seconds);
        if (!Number.isFinite(value) || value < 0) {
            return "unknown";
        }
        if (value < 5) {
            return "just now";
        }
        if (value < 60) {
            return Math.floor(value) + "s ago";
        }
        const minutes = Math.floor(value / 60);
        if (minutes < 60) {
            return minutes + "m ago";
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 24) {
            return hours + "h ago";
        }
        return Math.floor(hours / 24) + "d ago";
    }

    function formatTimestamp(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return chartTimestampFormatter.format(date);
    }

    function formatRelativeTime(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        const difference = Math.round((date.getTime() - Date.now()) / 1000);
        const absolute = Math.abs(difference);
        if (absolute < 60) {
            return relativeTimeFormatter.format(difference, "second");
        }
        if (absolute < 3600) {
            return relativeTimeFormatter.format(
                Math.round(difference / 60), "minute"
            );
        }
        if (absolute < 86400) {
            return relativeTimeFormatter.format(
                Math.round(difference / 3600), "hour"
            );
        }
        return relativeTimeFormatter.format(
            Math.round(difference / 86400), "day"
        );
    }

    function setMetric(element, label, value, limit, exceeded) {
        let text = label + ": " + formatNumber(value) + "%";
        if (limit !== null && limit !== undefined) {
            text += " \u00b7 limit " + formatNumber(limit) + "%";
        }
        element.textContent = text;
        element.classList.toggle("text-danger", exceeded);
        element.classList.toggle("fw-semibold", exceeded);
    }

    function updateCard(card, server) {
        const thresholds = server.thresholds;
        const exceeded = new Set(server.exceeded || []);

        card.querySelector(".server-name").textContent = server.instance_name;

        const badge = card.querySelector(".status-badge");
        badge.className = "badge status-badge";
        if (server.status === "offline") {
            badge.textContent = "Offline";
            badge.classList.add("bg-secondary");
            badge.classList.remove("d-none");
        } else if (server.status === "critical") {
            badge.textContent = "Threshold exceeded";
            badge.classList.add("bg-danger");
            badge.classList.remove("d-none");
        } else {
            badge.classList.add("d-none");
        }

        card.classList.toggle("opacity-75", server.status === "offline");
        card.querySelector(".card").classList.toggle(
            "border-danger", server.status === "critical"
        );

        setMetric(
            card.querySelector(".metric-cpu"),
            "CPU",
            server.cpu,
            thresholds ? thresholds.cpu : null,
            exceeded.has("cpu")
        );
        setMetric(
            card.querySelector(".metric-memory"),
            "Memory",
            server.memory,
            thresholds ? thresholds.memory : null,
            exceeded.has("memory")
        );
        setMetric(
            card.querySelector(".metric-disk"),
            "Disk",
            server.disk,
            thresholds ? thresholds.disk : null,
            exceeded.has("disk")
        );

        const lastSeen = card.querySelector(".last-seen");
        lastSeen.textContent = "Last seen " + formatAge(server.age_seconds);
        lastSeen.title = new Date(server.timing).toLocaleString();

        const thresholdLink = card.querySelector(".threshold-link");
        if (state.isStaff) {
            const base = config.thresholdsUrl.endsWith("/")
                ? config.thresholdsUrl
                : config.thresholdsUrl + "/";
            if (thresholds && thresholds.id !== null) {
                thresholdLink.href = base + thresholds.id + "/edit/";
                thresholdLink.textContent = "Edit threshold";
            } else {
                thresholdLink.href = base + "add/?server="
                    + encodeURIComponent(server.instance_name);
                thresholdLink.textContent = "Add threshold";
            }
            thresholdLink.classList.remove("d-none");
        } else {
            thresholdLink.classList.add("d-none");
            thresholdLink.removeAttribute("href");
        }
    }

    function renderCards(servers) {
        const container = document.getElementById("status-cards-container");
        const template = document.getElementById("server-card-template");
        if (!container || !template) {
            return;
        }

        const seen = new Set();
        servers.forEach(function (server) {
            seen.add(server.instance_name);
            let card = state.cards.get(server.instance_name);
            if (!card) {
                card = template.content.firstElementChild.cloneNode(true);
                container.appendChild(card);
                state.cards.set(server.instance_name, card);
            }
            updateCard(card, server);
        });

        state.cards.forEach(function (card, instanceName) {
            if (!seen.has(instanceName)) {
                card.remove();
                state.cards.delete(instanceName);
            }
        });
    }

    async function loadLatestMetrics() {
        try {
            const servers = await getJSON(config.latestUrl);
            if (redirecting) {
                return;
            }
            hideError("metrics-error");
            renderCards(servers);
        } catch (error) {
            if (redirecting) {
                return;
            }
            showError("metrics-error", "Failed to load server metrics.");
            console.error("Error while loading metrics:", error);
        }
    }

    function renderAlerts(alerts) {
        const list = document.getElementById("alerts-list");
        if (!list) {
            return;
        }

        list.replaceChildren();
        if (!alerts.length) {
            const empty = document.createElement("li");
            empty.className = "list-group-item text-muted";
            empty.textContent = "No alerts yet.";
            list.appendChild(empty);
            return;
        }

        alerts.forEach(function (alert) {
            const item = document.createElement("li");
            item.className = "list-group-item d-flex justify-content-between "
                + "align-items-start gap-2";

            const body = document.createElement("div");
            body.className = "me-auto";

            const title = document.createElement("div");
            title.className = "fw-bold text-danger";
            title.textContent = alert.metric_type.toUpperCase()
                + " usage on " + alert.server_instance;

            const value = document.createElement("div");
            value.className = "small";
            value.textContent = "Value: " + formatNumber(alert.value) + "%";

            const time = document.createElement("span");
            time.className = "badge bg-secondary";
            time.textContent = formatRelativeTime(alert.trigger_time);
            time.title = new Date(alert.trigger_time).toLocaleString();

            body.append(title, value);
            item.append(body, time);
            list.appendChild(item);
        });
    }

    async function loadAlerts() {
        try {
            const alerts = await getJSON(config.alertsUrl);
            if (redirecting) {
                return;
            }
            hideError("alerts-error");
            renderAlerts(alerts);
        } catch (error) {
            if (redirecting) {
                return;
            }
            showError("alerts-error", "Failed to load alerts.");
            console.error("Error while loading alerts:", error);
        }
    }

    function renderChart() {
        if (typeof Chart === "undefined") {
            showError("chart-error", "Chart library failed to load.");
            return;
        }

        const data = state.chartData;
        if (!data) {
            return;
        }

        const canvas = document.getElementById("metricChart");
        const empty = document.getElementById("chart-empty");
        if (!canvas || !empty) {
            return;
        }

        const hasData = data.series.some(function (server) {
            const values = server[state.metric];
            return Array.isArray(values) && values.some(function (value) {
                return value !== null;
            });
        });

        if (!data.timestamps.length || !hasData) {
            if (state.chart) {
                state.chart.destroy();
                state.chart = null;
            }
            canvas.classList.add("d-none");
            empty.classList.remove("d-none");
            return;
        }

        empty.classList.add("d-none");
        canvas.classList.remove("d-none");

        const labels = data.timestamps.map(formatTimestamp);
        const datasets = data.series.map(function (server, index) {
            const color = COLORS[index % COLORS.length];
            return {
                label: server.instance_name,
                data: server[state.metric],
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.25,
                spanGaps: true,
            };
        });

        if (!state.chart) {
            state.chart = new Chart(canvas, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: {
                        mode: "index",
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: {
                                boxWidth: 12,
                                usePointStyle: true,
                            },
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return context.dataset.label + ": "
                                        + formatNumber(context.parsed.y) + "%";
                                },
                            },
                        },
                    },
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            ticks: {
                                callback: function (value) {
                                    return value + "%";
                                },
                            },
                        },
                        x: {
                            ticks: {
                                autoSkip: true,
                                maxTicksLimit: 10,
                                maxRotation: 0,
                            },
                        },
                    },
                },
            });
        } else {
            state.chart.data.labels = labels;
            state.chart.data.datasets = datasets;
            state.chart.update("none");
        }
    }

    async function loadChart() {
        if (typeof Chart === "undefined") {
            showError("chart-error", "Chart library failed to load.");
            return;
        }

        const requestId = ++state.chartRequestId;
        if (state.chartController) {
            state.chartController.abort();
        }
        const controller = new AbortController();
        state.chartController = controller;

        try {
            const data = await getJSON(
                config.timeseriesUrl + "?range=" + encodeURIComponent(state.range),
                { signal: controller.signal }
            );
            if (redirecting || requestId !== state.chartRequestId) {
                return;
            }
            state.chartData = data;
            hideError("chart-error");
            renderChart();
        } catch (error) {
            if (
                error.name === "AbortError"
                || redirecting
                || requestId !== state.chartRequestId
            ) {
                return;
            }
            showError("chart-error", "Failed to load chart data.");
            console.error("Error while loading chart:", error);
        } finally {
            if (state.chartController === controller) {
                state.chartController = null;
            }
        }
    }

    function createPoller(task, interval) {
        let timer = null;
        let running = false;

        async function run() {
            window.clearTimeout(timer);
            timer = null;

            if (document.hidden || running) {
                return;
            }

            running = true;
            try {
                await task();
            } catch (error) {
                console.error(error);
            } finally {
                running = false;
                if (!document.hidden) {
                    timer = window.setTimeout(run, interval);
                }
            }
        }

        return {
            start: run,
            refreshNow: run,
        };
    }

    function init() {
        const metricSelect = document.getElementById("metric-select");
        const rangeSelect = document.getElementById("range-select");
        if (metricSelect) {
            state.metric = metricSelect.value || "cpu";
            metricSelect.addEventListener("change", function () {
                state.metric = metricSelect.value;
                renderChart();
            });
        }
        if (rangeSelect) {
            state.range = rangeSelect.value || "48h";
            rangeSelect.addEventListener("change", function () {
                state.range = rangeSelect.value;
                loadChart();
            });
        }

        const pollers = [
            createPoller(loadLatestMetrics, 10000),
            createPoller(loadAlerts, 20000),
        ];
        if (typeof Chart === "undefined") {
            showError("chart-error", "Chart library failed to load.");
        } else {
            pollers.push(createPoller(loadChart, 300000));
        }

        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) {
                pollers.forEach(function (poller) {
                    poller.refreshNow();
                });
            }
        });

        pollers.forEach(function (poller) {
            poller.start();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
