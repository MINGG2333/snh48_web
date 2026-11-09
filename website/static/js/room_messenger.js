/* ═══════════════════════════════════════════════════════════════════════════
   房间信使 / Room Messenger
   个人号登录、频道选择、聊天记录、即时/定时/批量发送
   ═══════════════════════════════════════════════════════════════════════════*/
(function () {
    "use strict";

    var BOOT = window.ROOM_MESSENGER_BOOT || {};
    var API_ROOT = "/api/room-messenger";
    var $ = function (id) { return document.getElementById(id); };
    var S = {
        verified: false,
        enabled: Boolean(BOOT.enabled),
        node: BOOT.node || "",
        limits: {
            min_interval: 1,
            default_interval: 60,
            max_jitter: 0,
            max_batch: 0,
            daily_cap: 0,
            history_poll: 20,
            max_text_length: 1000,
            timezone: "Asia/Shanghai",
            confirm_word: "确认发送"
        },
        accounts: [],
        binding: {},
        accountValid: null,
        bigSmall: [],
        deleteTarget: null,
        deleteTargets: [],
        selectMode: false,
        selectedIds: new Set(),
        editingJobId: null,
        lastAlertKey: "",
        dismissedAlertKey: "",
        channel: null,
        messages: [],
        nextTime: 0,
        nearBottom: true,
        loadingMessages: false,
        loadingOlder: false,
        recent: [],
        tab: "recent",
        catalog: { rows: [], offset: 0, total: 0, query: "", loading: false },
        openMemberId: "",
        jobs: [],
        jobsOpen: false,
        queueTab: "jobs",
        sentLog: [],
        scheduleMode: "once",
        pollTimer: null,
        jobsTimer: null,
        searchTimer: null,
        smsTimer: null,
        dailySent: 0
    };

    function track(eventType, data) {
        try {
            if (window._trackEvent) {
                window._trackEvent(eventType, Object.assign({ area: "room_messenger" }, data || {}));
            }
        } catch (error) { /* tracking is best effort */ }
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function safeUrl(value) {
        var url = String(value || "").trim();
        return /^https?:\/\//i.test(url) ? url : "";
    }

    function toast(message, kind) {
        var el = $("toast");
        el.textContent = String(message || "");
        el.className = "rm-toast" + (kind === "error" ? " is-error" : kind === "success" ? " is-success" : "");
        el.hidden = false;
        clearTimeout(el._timer);
        el._timer = setTimeout(function () { el.hidden = true; }, kind === "error" ? 5200 : 3200);
    }

    function showError(el, message) {
        if (!el) return;
        el.textContent = String(message || "");
        el.hidden = !message;
    }

    function formatTime(ms) {
        var date = new Date(Number(ms) || 0);
        if (isNaN(date.getTime()) || !ms) return "";
        var hh = String(date.getHours()).padStart(2, "0");
        var mm = String(date.getMinutes()).padStart(2, "0");
        return hh + ":" + mm;
    }

    function dateKey(ms) {
        var date = new Date(Number(ms) || 0);
        if (isNaN(date.getTime()) || !ms) return "";
        return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
    }

    function dayLabel(key) {
        var today = new Date();
        var todayKey = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
        var yesterday = new Date(today.getTime() - 86400000);
        var yKey = yesterday.getFullYear() + "-" + String(yesterday.getMonth() + 1).padStart(2, "0") + "-" + String(yesterday.getDate()).padStart(2, "0");
        if (key === todayKey) return "今天";
        if (key === yKey) return "昨天";
        var parts = key.split("-");
        return parts[1] + "月" + parts[2] + "日";
    }

    function formatDateTime(value) {
        if (!value) return "";
        var date = new Date(Number(value) * 1000);
        if (isNaN(date.getTime())) return "";
        return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0") +
            " " + String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0") +
            ":" + String(date.getSeconds()).padStart(2, "0");
    }

    function formatIso(value) {
        if (!value) return "";
        var date = new Date(value);
        if (isNaN(date.getTime())) return String(value);
        return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0") +
            " " + String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0") + ":" + String(date.getSeconds()).padStart(2, "0");
    }

    function localInputValue(date) {
        return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0") +
            "T" + String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
    }

    function toShanghaiIso(value) {
        var text = String(value || "").trim();
        if (!text) return "";
        if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(text)) return text;
        if (text.length === 16) text += ":00";
        return text + "+08:00";
    }

    // ── API ────────────────────────────────────────────────────────────────
    function api(path, options) {
        options = options || {};
        var init = {
            method: options.method || "GET",
            credentials: "same-origin",
            cache: "no-store",
            headers: Object.assign({}, options.headers || {})
        };
        if (options.body !== undefined) {
            init.headers["Content-Type"] = "application/json";
            init.body = JSON.stringify(options.body);
        }
        return fetch(API_ROOT + path, init).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (data) {
                if (response.status === 401) {
                    showLogin("登录已失效，请重新输入密码");
                    throw new Error("登录已失效，请重新输入密码");
                }
                if (!response.ok) {
                    throw new Error((data && data.detail) || ("HTTP " + response.status));
                }
                return data;
            });
        });
    }

    // ── Login ──────────────────────────────────────────────────────────────
    function showLogin(message) {
        S.verified = false;
        S.channel = null;
        S.messages = [];
        S.nextTime = 0;
        S.selectMode = false;
        S.selectedIds.clear();
        $("app").hidden = true;
        $("loginOverlay").hidden = false;
        $("loginPassword").value = "";
        showError($("loginError"), message || "");
        stopTimers();
        setTimeout(function () { $("loginPassword").focus(); }, 30);
    }

    function showApp() {
        S.verified = true;
        $("loginOverlay").hidden = true;
        $("app").hidden = false;
    }

    function logoutPage() {
        api("/logout", { method: "POST", body: {} }).finally(function () {
            S.binding = {};
            S.channel = null;
            S.messages = [];
            showLogin("");
        });
    }

    function boot() {
        if (!S.enabled) {
            $("loginForm").querySelector("button[type=submit]").disabled = true;
            showError($("loginError"), "消息发送功能仅腾讯云私密站（cjy.plus）启用，当前节点不可用。");
            return;
        }
        api("/verify").then(function (data) {
            if (data && data.limits) S.limits = data.limits;
            showApp();
            loadAll();
        }).catch(function () {
            showLogin("");
        });
    }

    function login(event) {
        event.preventDefault();
        var password = $("loginPassword").value;
        if (!password) return;
        var button = $("loginSubmit");
        button.disabled = true;
        showError($("loginError"), "");
        track("login_attempt", { page: "room_messenger", action: "submit" });
        api("/login", { method: "POST", body: { password: password } }).then(function () {
            $("loginPassword").value = "";
            track("login_attempt", { page: "room_messenger", action: "success" });
            return api("/verify");
        }).then(function (data) {
            if (data && data.limits) S.limits = data.limits;
            showApp();
            loadAll();
        }).catch(function (error) {
            track("login_attempt", { page: "room_messenger", action: "fail" });
            showError($("loginError"), error.message || "密码错误");
            $("loginPassword").value = "";
        }).finally(function () {
            button.disabled = false;
        });
    }

    // ── Account ────────────────────────────────────────────────────────────
    function loadAll() {
        updateComposerState();
        loadAccount();
        loadRecent();
        loadJobs();
        if (S.tab === "catalog") loadCatalog(true);
        startJobsPolling();
    }

    function loadAccount() {
        return api("/account").then(function (data) {
            S.accounts = Array.isArray(data.accounts) ? data.accounts : [];
            S.binding = data.binding || {};
            S.accountValid = null;
            S.bigSmall = [];
            if (data.limits) S.limits = data.limits;
            if (typeof data.daily_sent === "number") S.dailySent = data.daily_sent;
            renderAccount();
            renderDailyMeter();
            renderAccountList();
            renderSwitchAccounts();
            updateComposerState();
            if (S.binding.account_id) probeAccount(true);
            if (S.channel && !S.messages.length) {
                initialLoad();
                startPolling();
            }
        }).catch(function (error) {
            if (S.verified) toast(error.message || "读取账号失败", "error");
        });
    }

    function renderAccount() {
        var bound = S.binding && S.binding.account_id;
        var account = null;
        if (bound) {
            account = S.accounts.find(function (item) { return String(item.id) === String(bound); }) || null;
        }
        $("accountAvatar").innerHTML = bound ? '<i class="fas fa-user-astronaut"></i>' : '<i class="fas fa-user"></i>';
        $("accountName").textContent = bound
            ? (S.binding.nickname || (account && account.nickname) || ("个人号 " + bound))
            : "未登录个人账号";
        var invalid = bound && S.accountValid === false;
        $("accountMeta").textContent = bound
            ? (invalid ? "Token 已失效，请重新登录" : ("绑定个人号 · " + bound))
            : "登录后即可发送房间消息";
        $("accountLoginBtn").innerHTML = invalid
            ? '<i class="fas fa-key"></i> 重新登录'
            : (bound ? '<i class="fas fa-right-left"></i> 切换' : '<i class="fas fa-key"></i> 登录');
        $("accountProbeBtn").hidden = !bound;
        $("accountUnbindBtn").hidden = !bound;
        $("tokenWarning").hidden = !invalid;
    }

    function renderAccountList() {
        var wrap = $("accountList");
        if (!S.accounts.length) {
            wrap.innerHTML = '<div class="rm-empty-small">账号库中还没有个人号，请先登录一个账号</div>';
            return;
        }
        wrap.innerHTML = "";
        S.accounts.forEach(function (account) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "rm-account-option";
            var active = S.binding && String(S.binding.account_id) === String(account.id);
            button.innerHTML =
                '<span class="rm-account-option-name">' + escapeHtml(account.nickname || ("个人号 " + account.id)) +
                (active ? ' <i class="fas fa-check" style="color:var(--primary)"></i>' : "") + '</span>' +
                '<span class="rm-account-option-meta">' + escapeHtml(account.id) +
                (account.has_token ? "" : " · Token 缺失") + '</span>';
            button.addEventListener("click", function () {
                bindAccount(account.id);
            });
            wrap.appendChild(button);
        });
    }

    function bindAccount(accountId) {
        api("/account/bind", { method: "POST", body: { account_id: accountId } }).then(function (data) {
            S.binding = data.binding || {};
            renderAccount();
            updateComposerState();
            closeModal("accountModal");
            toast("已绑定个人账号", "success");
            track("admin_update", { page: "room_messenger", action: "bind_account" });
        }).catch(function (error) {
            showError($("accountFormError"), error.message);
        });
    }

    function openAccountModal() {
        showError($("accountFormError"), "");
        showError($("loginError"), "");
        clearInterval(S.smsTimer);
        $("smsBtn").disabled = false;
        $("smsBtn").textContent = "发送验证码";
        S.loginSession = null;
        $("accountPhoneStep").hidden = false;
        $("securityStep").hidden = true;
        $("codeStep").hidden = true;
        $("smsStatus").textContent = "";
        $("accountCode").value = "";
        renderAccountList();
        renderSwitchAccounts();
        openModal("accountModal");
        if (S.binding.account_id) probeAccount(true);
    }

    function sendSms() {
        var phone = $("accountPhone").value.trim();
        var area = $("accountArea").value.trim() || "86";
        if (!/^\d{5,15}$/.test(phone)) {
            showError($("accountFormError"), "请输入有效手机号");
            return;
        }
        var button = $("smsBtn");
        button.disabled = true;
        showError($("accountFormError"), "");
        $("smsStatus").textContent = "正在发送…";
        api("/account/send-sms", { method: "POST", body: { phone: phone, area: area } }).then(function (data) {
            S.loginSession = data.session_id || "";
            if (data.state === "awaiting_security") {
                $("securityStep").hidden = false;
                $("codeStep").hidden = true;
                $("securityQuestion").textContent = data.question || "请完成安全验证";
                var select = $("securityOption");
                select.innerHTML = "";
                (data.options || []).forEach(function (option) {
                    var item = document.createElement("option");
                    item.value = option.option;
                    item.textContent = option.value || option.option;
                    select.appendChild(item);
                });
                $("smsStatus").textContent = "";
                toast("需要完成安全验证", "error");
            } else {
                $("securityStep").hidden = true;
                $("codeStep").hidden = false;
                $("smsStatus").textContent = "验证码已发送";
                startSmsCountdown(60);
                toast("验证码已发送", "success");
            }
            track("admin_update", { page: "room_messenger", action: "send_sms", state: data.state || "" });
        }).catch(function (error) {
            $("smsStatus").textContent = "";
            showError($("accountFormError"), error.message);
        }).finally(function () {
            button.disabled = false;
        });
    }

    function startSmsCountdown(seconds) {
        clearInterval(S.smsTimer);
        var button = $("smsBtn");
        var remaining = seconds;
        button.disabled = true;
        button.textContent = remaining + "s";
        S.smsTimer = setInterval(function () {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(S.smsTimer);
                button.disabled = false;
                button.textContent = "重新发送";
            } else {
                button.textContent = remaining + "s";
            }
        }, 1000);
    }

    function submitSecurity() {
        var option = $("securityOption").value;
        if (!option) return;
        showError($("accountFormError"), "");
        api("/account/security-answer", { method: "POST", body: { session_id: S.loginSession || "", option: option } })
            .then(function (data) {
                if (data.state === "awaiting_code") {
                    $("securityStep").hidden = true;
                    $("codeStep").hidden = false;
                    toast("安全验证通过，请查收验证码", "success");
                }
            })
            .catch(function (error) { showError($("accountFormError"), error.message); });
    }

    function verifyCode() {
        var code = $("accountCode").value.trim();
        if (!/^\d{4,8}$/.test(code)) {
            showError($("accountFormError"), "请输入有效验证码");
            return;
        }
        var button = $("verifyBtn");
        button.disabled = true;
        showError($("accountFormError"), "");
        var sessionId = S.loginSession;
        if (!sessionId) {
            // The bridge session id is returned by send-sms; if it was not
            // captured (older response shape), fail clearly instead of guessing.
            showError($("accountFormError"), "登录会话已失效，请重新发送验证码");
            button.disabled = false;
            return;
        }
        api("/account/verify-code", { method: "POST", body: { session_id: sessionId, code: code } }).then(function (data) {
            S.binding = data.binding || {};
            S.loginSession = null;
            closeModal("accountModal");
            toast("个人账号已绑定", "success");
            track("admin_update", { page: "room_messenger", action: "login_success" });
            loadAccount();
            loadRecent();
        }).catch(function (error) {
            showError($("accountFormError"), error.message);
        }).finally(function () {
            button.disabled = false;
        });
    }

    function probeAccount(silent) {
        var accountId = (S.binding || {}).account_id || "";
        if (!accountId) return;
        api("/account/probe", { method: "POST", body: { account_id: accountId } })
            .then(function (data) {
                var wasValid = S.accountValid;
                S.accountValid = Boolean(data.valid);
                S.bigSmall = Array.isArray(data.big_small) ? data.big_small : [];
                if (data.valid && !S.binding.nickname && data.nickname) {
                    S.binding.nickname = data.nickname;
                }
                renderAccount();
                renderSwitchAccounts();
                if (!data.valid) {
                    $("tokenWarningText").textContent = "个人号 Token 已失效：" + (data.message || "请重新登录");
                    if (!silent || wasValid !== false) toast("个人号 Token 已失效，请重新登录", "error");
                } else if (!silent) {
                    toast("Token 有效：" + (data.nickname || data.account_id), "success");
                }
            })
            .catch(function (error) {
                if (!silent) toast(error.message, "error");
            });
    }

    function renderSwitchAccounts() {
        var wrap = $("switchAccountWrap");
        var list = $("switchAccountList");
        var rows = S.bigSmall || [];
        if (!S.binding.account_id || rows.length < 2) {
            wrap.hidden = true;
            list.innerHTML = "";
            return;
        }
        wrap.hidden = false;
        list.innerHTML = "";
        rows.forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "rm-account-option";
            var role = item.role === "small" ? "小号" : "大号";
            button.innerHTML =
                '<span class="rm-account-option-name">' + escapeHtml(item.nickname || item.user_id) +
                (item.current ? ' <i class="fas fa-check" style="color:var(--primary)"></i>' : "") + '</span>' +
                '<span class="rm-account-option-meta">' + role + ' · ' + escapeHtml(item.user_id) + '</span>';
            button.disabled = Boolean(item.current);
            button.addEventListener("click", function () {
                if (!item.current) switchAccount(item.user_id);
            });
            list.appendChild(button);
        });
    }

    function switchAccount(targetUserId) {
        var button = $("accountLoginBtn");
        button.disabled = true;
        showError($("accountFormError"), "");
        api("/account/switch", {
            method: "POST",
            body: { target_user_id: String(targetUserId) }
        }).then(function (data) {
            S.binding = data.binding || {};
            S.accountValid = null;
            S.bigSmall = [];
            closeModal("accountModal");
            toast("已切换到 " + ((S.binding || {}).nickname || targetUserId), "success");
            track("admin_update", { page: "room_messenger", action: "switch_account" });
            loadAccount();
            loadRecent();
            if (S.channel) initialLoad();
        }).catch(function (error) {
            showError($("accountFormError"), error.message);
        }).finally(function () {
            button.disabled = false;
        });
    }

    function unbindAccount() {
        api("/account/unbind", { method: "POST", body: {} }).then(function () {
            S.binding = {};
            renderAccount();
            updateComposerState();
            toast("已解除页面绑定，账号仍保留在账号库", "success");
            track("admin_update", { page: "room_messenger", action: "unbind_account" });
        }).catch(function (error) { toast(error.message, "error"); });
    }

    function renderDailyMeter() {
        var cap = (S.limits && S.limits.daily_cap) || 0;
        $("dailyMeter").textContent = "今日发送 " + (S.dailySent || 0) + " / " + (cap > 0 ? cap : "不限");
    }

    // ── Sidebar tabs / recent / catalog ────────────────────────────────────
    function setTab(tab) {
        S.tab = tab;
        Array.prototype.forEach.call(document.querySelectorAll(".rm-tab"), function (button) {
            button.classList.toggle("is-active", button.dataset.tab === tab);
        });
        if (tab === "recent") {
            renderRecent();
        } else {
            if (!S.catalog.rows.length) loadCatalog(true);
            else renderCatalog();
        }
        track("admin_filter", { page: "room_messenger", action: "tab", tab: tab });
    }

    function loadRecent() {
        return api("/recent").then(function (data) {
            S.recent = Array.isArray(data.channels) ? data.channels : [];
            if (S.tab === "recent") renderRecent();
        }).catch(function (error) {
            if (S.verified && error.message !== "请先登录并绑定个人账号") {
                // A missing binding is a normal first-run state.
            }
        });
    }

    function renderRecent() {
        var wrap = $("channelList");
        var query = $("channelSearch").value.trim().toLowerCase();
        var rows = S.recent.filter(function (item) {
            if (!query) return true;
            return (String(item.member_name) + " " + String(item.channel_id) + " " + String(item.room_label)).toLowerCase().indexOf(query) >= 0;
        });
        if (!rows.length) {
            wrap.innerHTML = '<div class="rm-empty-small">' + (query ? "没有匹配的常用频道" : "还没有常用频道，去“成员目录”选择成员") + "</div>";
            return;
        }
        wrap.innerHTML = "";
        rows.forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "rm-channel-item" + (S.channel && String(S.channel.channel_id) === String(item.channel_id) ? " is-active" : "");
            button.innerHTML =
                '<span class="rm-channel-avatar"><i class="fas fa-comment"></i></span>' +
                '<span class="rm-channel-text"><span class="rm-channel-name">' + escapeHtml(item.member_name || ("频道 " + item.channel_id)) + '</span>' +
                '<span class="rm-channel-sub">' + escapeHtml((item.group ? item.group + " · " : "") + (item.room_label || "")) + '</span></span>' +
                '<span class="rm-room-type ' + (item.room_type === "small" ? "small" : "") + '">' + (item.room_type === "small" ? "小房间" : "公开") + '</span>';
            button.addEventListener("click", function () {
                selectChannel({
                    channel_id: item.channel_id,
                    server_id: item.server_id,
                    member_id: item.member_id,
                    member_name: item.member_name,
                    group: item.group,
                    room_type: item.room_type,
                    room_label: item.room_label
                });
            });
            wrap.appendChild(button);
        });
    }

    function loadCatalog(reset) {
        if (S.catalog.loading) return;
        if (reset) {
            S.catalog.offset = 0;
            S.catalog.rows = [];
        }
        S.catalog.loading = true;
        var query = $("channelSearch").value.trim();
        api("/catalog?q=" + encodeURIComponent(query) + "&limit=40&offset=" + S.catalog.offset)
            .then(function (data) {
                var rows = Array.isArray(data.members) ? data.members : [];
                S.catalog.rows = S.catalog.offset === 0 ? rows : S.catalog.rows.concat(rows);
                S.catalog.total = data.total || S.catalog.rows.length;
                S.catalog.offset = S.catalog.rows.length;
                S.catalog.query = query;
                renderCatalog();
            })
            .catch(function (error) {
                if (S.verified) toast(error.message || "读取成员目录失败", "error");
            })
            .finally(function () { S.catalog.loading = false; });
    }

    function renderCatalog() {
        var wrap = $("channelList");
        if (!S.catalog.rows.length) {
            wrap.innerHTML = '<div class="rm-empty-small">没有匹配的成员</div>';
            return;
        }
        wrap.innerHTML = "";
        S.catalog.rows.forEach(function (member) {
            var row = document.createElement("button");
            row.type = "button";
            row.className = "rm-member-row";
            row.innerHTML =
                '<span class="rm-member-avatar">' + escapeHtml((member.name || "?").slice(0, 1)) + '</span>' +
                '<span class="rm-member-name">' + escapeHtml(member.name) + '<span class="rm-member-group">' + escapeHtml(member.group || "") + '</span></span>' +
                '<span class="rm-room-type">' + (member.rooms || []).length + ' 个频道</span>';
            row.addEventListener("click", function () {
                S.openMemberId = S.openMemberId === String(member.id) ? "" : String(member.id);
                renderCatalog();
            });
            wrap.appendChild(row);
            if (S.openMemberId === String(member.id)) {
                var rooms = document.createElement("div");
                rooms.className = "rm-member-rooms";
                (member.rooms || []).forEach(function (room) {
                    var roomButton = document.createElement("button");
                    roomButton.type = "button";
                    roomButton.className = "rm-member-room";
                    roomButton.innerHTML =
                        '<span><i class="fas ' + (room.room_type === "small" ? "fa-door-closed" : "fa-door-open") + '"></i> ' +
                        escapeHtml(room.room_label || (room.room_type === "small" ? "小房间" : "公开房间")) + '</span>' +
                        '<span class="rm-room-type ' + (room.room_type === "small" ? "small" : "") + '">' + escapeHtml(room.channel_id) + '</span>';
                    roomButton.addEventListener("click", function () {
                        selectChannel({
                            channel_id: room.channel_id,
                            server_id: room.server_id,
                            member_id: member.id,
                            member_name: member.name,
                            group: member.group,
                            room_type: room.room_type,
                            room_label: room.room_label
                        });
                    });
                    rooms.appendChild(roomButton);
                });
                wrap.appendChild(rooms);
            }
        });
        if (S.catalog.offset < S.catalog.total) {
            var more = document.createElement("button");
            more.type = "button";
            more.className = "rm-load-older";
            more.textContent = "加载更多成员（" + S.catalog.offset + " / " + S.catalog.total + "）";
            more.addEventListener("click", function () { loadCatalog(false); });
            wrap.appendChild(more);
        }
    }

    function selectChannel(channel) {
        if (!channel || !channel.channel_id) return;
        S.channel = channel;
        S.messages = [];
        S.nextTime = 0;
        S.nearBottom = true;
        S.selectMode = false;
        S.selectedIds.clear();
        $("selectionBar").hidden = true;
        $("selectModeBtn").classList.remove("is-active");
        $("channelTitle").textContent = channel.member_name || ("频道 " + channel.channel_id);
        $("channelSubtitle").textContent = [
            channel.group || "",
            channel.room_label || (channel.room_type === "small" ? "小房间" : "公开房间"),
            channel.channel_id
        ].filter(Boolean).join(" · ");
        $("chatEmpty").hidden = true;
        $("messageList").innerHTML = "";
        updateComposerState();
        closeSidebar();
        if (!S.binding || !S.binding.account_id) {
            $("chatEmpty").hidden = false;
            $("chatEmpty").querySelector("h3").textContent = "请先绑定个人账号";
            $("chatEmpty").querySelector("p").textContent = "绑定后可读取该频道最近消息并发送。";
            toast("请先在左上角登录并绑定个人账号", "error");
            return;
        }
        api("/recent", {
            method: "POST",
            body: {
                channel_id: channel.channel_id,
                server_id: channel.server_id,
                member_id: channel.member_id,
                member_name: channel.member_name,
                group: channel.group,
                room_type: channel.room_type,
                room_label: channel.room_label
            }
        }).then(function (data) {
            S.recent = Array.isArray(data.channels) ? data.channels : S.recent;
            if (S.tab === "recent") renderRecent();
        }).catch(function () { /* recent is best effort */ });
        initialLoad();
        startPolling();
        track("admin_filter", { page: "room_messenger", action: "select_channel", room_type: channel.room_type || "" });
    }

    // ── Messages ───────────────────────────────────────────────────────────
    function messageKey(item) {
        return String(item.id || item.server_id || (item.time + "|" + item.sender_id + "|" + item.text));
    }

    function initialLoad() {
        if (!S.channel) return;
        S.loadingMessages = true;
        api("/messages?channel_id=" + encodeURIComponent(S.channel.channel_id) +
            "&server_id=" + encodeURIComponent(S.channel.server_id || "") + "&next_time=0&limit=50")
            .then(function (data) {
                S.messages = Array.isArray(data.messages) ? data.messages : [];
                S.nextTime = Number(data.next_time) || 0;
                renderMessages();
                scrollToBottom(true);
            })
            .catch(function (error) {
                if (looksLikeTokenError(error.message)) markTokenInvalid(error.message);
                toast(error.message || "读取聊天记录失败", "error");
            })
            .finally(function () { S.loadingMessages = false; });
    }

    function pollMessages() {
        if (!S.channel || document.hidden || S.loadingMessages) return;
        api("/messages?channel_id=" + encodeURIComponent(S.channel.channel_id) +
            "&server_id=" + encodeURIComponent(S.channel.server_id || "") + "&next_time=0&limit=50")
            .then(function (data) {
                var fresh = Array.isArray(data.messages) ? data.messages : [];
                var known = new Set(S.messages.map(messageKey));
                var added = fresh.filter(function (item) { return !known.has(messageKey(item)); });
                if (!added.length) return;
                var chat = $("chat");
                var previousTop = chat.scrollTop;
                var wasNearBottom = S.nearBottom;
                S.messages = S.messages.concat(added).sort(function (a, b) { return (a.time || 0) - (b.time || 0); });
                renderMessages();
                if (wasNearBottom) {
                    scrollToBottom(true);
                } else {
                    chat.scrollTop = previousTop;
                    $("jumpLatest").hidden = false;
                }
            })
            .catch(function () { /* polling errors stay quiet */ });
    }

    function loadOlder() {
        if (!S.channel || !S.nextTime || S.loadingOlder) return;
        S.loadingOlder = true;
        var chat = $("chat");
        var previousHeight = chat.scrollHeight;
        var previousTop = chat.scrollTop;
        api("/messages?channel_id=" + encodeURIComponent(S.channel.channel_id) +
            "&server_id=" + encodeURIComponent(S.channel.server_id || "") + "&next_time=" + S.nextTime + "&limit=50")
            .then(function (data) {
                var older = Array.isArray(data.messages) ? data.messages : [];
                var known = new Set(S.messages.map(messageKey));
                var merged = older.filter(function (item) { return !known.has(messageKey(item)); });
                S.messages = merged.concat(S.messages).sort(function (a, b) { return (a.time || 0) - (b.time || 0); });
                S.nextTime = Number(data.next_time) || 0;
                renderMessages();
                chat.scrollTop = chat.scrollHeight - previousHeight + previousTop;
            })
            .catch(function (error) { toast(error.message || "加载更早消息失败", "error"); })
            .finally(function () { S.loadingOlder = false; });
    }

    function renderMessages() {
        var list = $("messageList");
        list.innerHTML = "";
        if (!S.messages.length) {
            list.innerHTML = '<div class="rm-empty-small">这个频道暂无消息，或当前账号无权读取</div>';
            return;
        }
        if (S.nextTime) {
            var older = document.createElement("button");
            older.type = "button";
            older.className = "rm-load-older";
            older.textContent = "加载更早的消息";
            older.addEventListener("click", loadOlder);
            list.appendChild(older);
        }
        var lastDay = "";
        var ownId = String((S.binding || {}).account_id || "");
        S.messages.forEach(function (item) {
            var day = dateKey(item.time);
            if (day && day !== lastDay) {
                lastDay = day;
                var separator = document.createElement("div");
                separator.className = "rm-day-separator";
                separator.textContent = dayLabel(day);
                list.appendChild(separator);
            }
            list.appendChild(renderMessage(item, ownId));
        });
    }

    function renderMessage(item, ownId) {
        var wrapper = document.createElement("div");
        var self = ownId && String(item.sender_id || "") === ownId;
        wrapper.className = "rm-msg" + (self ? " is-self" : "");
        wrapper.dataset.msgId = item.msg_id_client || "";
        if (S.selectMode && item.msg_id_client && S.selectedIds.has(item.msg_id_client)) {
            wrapper.classList.add("is-selected");
        }
        if (item.type === "GIFT_TEXT") wrapper.classList.add("is-gift");
        if (item.type === "AUDIO" || item.type === "AUDIO_REPLY" || item.type === "AUDIO_GIFT_REPLY") wrapper.classList.add("is-voice");
        if (item.type === "IMAGE" || item.type === "VIDEO" || item.type === "EXPRESSIMAGE") wrapper.classList.add("is-media");

        var avatar = document.createElement("div");
        avatar.className = "rm-msg-avatar";
        avatar.textContent = (item.sender_name || "?").slice(0, 1);
        wrapper.appendChild(avatar);

        var body = document.createElement("div");
        body.className = "rm-msg-body";
        var meta = document.createElement("div");
        meta.className = "rm-msg-meta";
        var sender = document.createElement("span");
        sender.className = "rm-msg-sender";
        sender.textContent = item.sender_name || ("用户 " + (item.sender_id || "?"));
        var time = document.createElement("span");
        time.className = "rm-msg-time";
        time.textContent = formatTime(item.time);
        meta.appendChild(sender);
        meta.appendChild(time);
        if (S.selectMode && self && item.msg_id_client && !item.deleted) {
            var selectButton = document.createElement("button");
            selectButton.type = "button";
            selectButton.className = "rm-msg-select";
            selectButton.title = "选择这条消息";
            var selected = S.selectedIds.has(item.msg_id_client);
            selectButton.innerHTML = selected
                ? '<i class="fas fa-square-check"></i>'
                : '<i class="fas fa-square"></i>';
            selectButton.addEventListener("click", function () { toggleMessageSelection(item); });
            meta.appendChild(selectButton);
        } else if (self && item.msg_id_client && item.time && !item.deleted) {
            var deleteButton = document.createElement("button");
            deleteButton.type = "button";
            deleteButton.className = "rm-msg-delete";
            deleteButton.title = "删除这条消息";
            deleteButton.innerHTML = '<i class="fas fa-trash-can"></i>';
            deleteButton.addEventListener("click", function () { openDeleteModal(item); });
            meta.appendChild(deleteButton);
        }
        body.appendChild(meta);

        var bubble = document.createElement("div");
        bubble.className = "rm-bubble";
        if (item.deleted) {
            wrapper.classList.add("is-deleted");
            var deletedLabel = document.createElement("span");
            deletedLabel.className = "rm-deleted-label";
            deletedLabel.innerHTML = '<i class="fas fa-ban"></i> 此消息已删除';
            bubble.appendChild(deletedLabel);
            if (item.text) {
                var original = document.createElement("div");
                original.className = "rm-deleted-original";
                original.textContent = item.text;
                bubble.appendChild(original);
            }
            body.appendChild(bubble);
            wrapper.appendChild(body);
            return wrapper;
        }
        if (item.reply_text) {
            var quote = document.createElement("div");
            quote.className = "rm-reply-quote";
            quote.textContent = "回复：" + item.reply_text;
            bubble.appendChild(quote);
        }
        var text = document.createElement("span");
        text.textContent = item.text || "";
        bubble.appendChild(text);
        var url = safeUrl(item.media_url);
        if (url) {
            bubble.appendChild(document.createTextNode(" "));
            var link = document.createElement("a");
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = item.type === "AUDIO" || item.type === "AUDIO_REPLY" || item.type === "AUDIO_GIFT_REPLY" ? "播放语音" : "查看媒体";
            bubble.appendChild(link);
        }
        body.appendChild(bubble);
        wrapper.appendChild(body);
        return wrapper;
    }

    function scrollToBottom(force) {
        var chat = $("chat");
        if (force || S.nearBottom) {
            chat.scrollTop = chat.scrollHeight;
            S.nearBottom = true;
            $("jumpLatest").hidden = true;
        }
    }

    function startPolling() {
        stopPolling();
        S.pollTimer = setInterval(pollMessages, Math.max(5, S.limits.history_poll || 20) * 1000);
    }

    function stopPolling() {
        clearInterval(S.pollTimer);
        S.pollTimer = null;
    }

    // ── Composer ───────────────────────────────────────────────────────────
    function updateComposerState() {
        var hasChannel = Boolean(S.channel && S.channel.channel_id && S.channel.server_id);
        var hasBinding = Boolean(S.binding && S.binding.account_id);
        var lock = $("composerLock");
        var composer = $("composer");
        if (hasChannel && hasBinding) {
            lock.hidden = true;
            composer.hidden = false;
        } else {
            lock.hidden = false;
            composer.hidden = true;
            if (hasChannel && !hasBinding) {
                lock.innerHTML = '<i class="fas fa-key"></i> 请先登录并绑定个人账号';
            } else if (!hasChannel && hasBinding) {
                lock.innerHTML = '<i class="fas fa-comments"></i> 请先从左侧选择频道';
            } else {
                lock.innerHTML = '<i class="fas fa-comments"></i> 请先选择频道并绑定个人账号';
            }
        }
    }

    function autoResizeComposer() {
        var input = $("messageInput");
        input.style.height = "auto";
        input.style.height = Math.min(180, Math.max(34, input.scrollHeight)) + "px";
        $("charCount").textContent = input.value.length + " / " + (S.limits.max_text_length || 1000);
    }

    function openSendModal() {
        var text = $("messageInput").value.trim();
        if (!text) return;
        if (text.length > (S.limits.max_text_length || 1000)) {
            toast("消息过长", "error");
            return;
        }
        $("sendTarget").textContent = "发送到：" + channelLabel();
        $("sendPreview").textContent = text;
        $("confirmWordLabel").textContent = S.limits.confirm_word || "确认发送";
        $("confirmWordInput").value = "";
        showError($("sendModalError"), "");
        openModal("sendModal");
        setTimeout(function () { $("confirmWordInput").focus(); }, 40);
        track("admin_modal", { page: "room_messenger", action: "send_confirm" });
    }

    function confirmSend() {
        var word = $("confirmWordInput").value.trim();
        var expected = S.limits.confirm_word || "确认发送";
        if (word !== expected) {
            showError($("sendModalError"), "请输入确认词“" + expected + "”");
            return;
        }
        var text = $("messageInput").value.trim();
        if (!text) {
            showError($("sendModalError"), "消息内容为空");
            return;
        }
        var button = $("confirmSendBtn");
        button.disabled = true;
        showError($("sendModalError"), "");
        api("/send", {
            method: "POST",
            body: {
                channel_id: S.channel.channel_id,
                server_id: S.channel.server_id,
                text: text,
                confirm: expected,
                channel: S.channel
            }
        }).then(function (data) {
            if (!data.ok) {
                throw new Error(data.error || "发送失败");
            }
            S.dailySent = data.daily_sent || (S.dailySent + 1);
            renderDailyMeter();
            $("messageInput").value = "";
            autoResizeComposer();
            closeModal("sendModal");
            toast("消息已发送", "success");
            track("admin_update", { page: "room_messenger", action: "send_now", result: "success" });
            loadSentLog();
            setTimeout(pollMessages, 900);
        }).catch(function (error) {
            if (looksLikeTokenError(error.message)) markTokenInvalid(error.message);
            showError($("sendModalError"), error.message || "发送失败");
            track("admin_update", { page: "room_messenger", action: "send_now", result: "fail" });
        }).finally(function () {
            button.disabled = false;
        });
    }

    // ── Delete message ─────────────────────────────────────────────────────
    function openDeleteModal(item) {
        if (!item || !item.msg_id_client) return;
        openDeleteTargets([item]);
    }

    function openBatchDeleteModal() {
        var targets = S.messages.filter(function (item) {
            return item.msg_id_client && S.selectedIds.has(item.msg_id_client) && !item.deleted;
        });
        if (!targets.length) {
            toast("请先勾选要删除的消息", "error");
            return;
        }
        openDeleteTargets(targets);
    }

    function openDeleteTargets(targets) {
        if (!targets || !targets.length) return;
        S.deleteTargets = targets;
        S.deleteTarget = targets.length === 1 ? targets[0] : null;
        $("deleteTarget").textContent = targets.length === 1
            ? ("频道：" + channelLabel())
            : ("批量删除 " + targets.length + " 条消息 · " + channelLabel());
        var preview = targets.map(function (item, index) {
            return (index + 1) + ". " + (item.text || "[非文本消息]");
        }).join("\n");
        if (preview.length > 1500) preview = preview.slice(0, 1500) + "\n…";
        $("deletePreview").textContent = preview;
        var word = S.limits.delete_confirm_word || "确认删除";
        $("deleteConfirmWordLabel").textContent = word;
        $("deleteConfirmWordInput").value = "";
        showError($("deleteModalError"), "");
        openModal("deleteModal");
        setTimeout(function () { $("deleteConfirmWordInput").focus(); }, 40);
        track("admin_modal", { page: "room_messenger", action: targets.length > 1 ? "batch_delete_confirm" : "delete_confirm" });
    }

    function confirmDelete() {
        var targets = (S.deleteTargets || []).slice();
        if (!targets.length && S.deleteTarget) targets = [S.deleteTarget];
        if (!targets.length) return;
        var expected = S.limits.delete_confirm_word || "确认删除";
        if ($("deleteConfirmWordInput").value.trim() !== expected) {
            showError($("deleteModalError"), "请输入确认词“" + expected + "”");
            return;
        }
        var button = $("confirmDeleteBtn");
        button.disabled = true;
        showError($("deleteModalError"), "");
        var request;
        if (targets.length === 1) {
            var item = targets[0];
            request = api("/delete", {
                method: "POST",
                body: {
                    account_id: (S.binding || {}).account_id || "",
                    channel_id: S.channel.channel_id,
                    msg_id_client: item.msg_id_client,
                    msg_time: item.time,
                    sender_id: item.sender_id || "",
                    sender_name: item.sender_name || "",
                    text: item.text || "",
                    confirm: expected
                }
            }).then(function (data) {
                item.deleted = true;
                item.deleted_at = (data.deleted && data.deleted.deleted_at) || new Date().toISOString();
                return { ok: true, count: 1 };
            });
        } else {
            request = api("/delete-batch", {
                method: "POST",
                body: {
                    account_id: (S.binding || {}).account_id || "",
                    channel_id: S.channel.channel_id,
                    items: targets.map(function (item) {
                        return {
                            msg_id_client: item.msg_id_client,
                            msg_time: item.time,
                            sender_id: item.sender_id || "",
                            sender_name: item.sender_name || "",
                            text: item.text || ""
                        };
                    }),
                    confirm: expected
                }
            }).then(function (data) {
                var deleted = new Set((data.deleted || []).map(function (item) { return item.msg_id_client; }));
                targets.forEach(function (item) {
                    if (deleted.has(item.msg_id_client)) {
                        item.deleted = true;
                        item.deleted_at = new Date().toISOString();
                    }
                });
                return { ok: true, count: targets.length };
            });
        }
        request.then(function (result) {
            if (targets.length > 1) setSelectMode(false);
            renderMessages();
            closeModal("deleteModal");
            S.deleteTarget = null;
            S.deleteTargets = [];
            toast("已删除 " + result.count + " 条消息，页面保留已删除标记", "success");
            track("admin_update", { page: "room_messenger", action: targets.length > 1 ? "batch_delete_message" : "delete_message" });
        }).catch(function (error) {
            if (looksLikeTokenError(error.message)) markTokenInvalid(error.message);
            showError($("deleteModalError"), error.message);
        }).finally(function () {
            button.disabled = false;
        });
    }

    function setSelectMode(enabled) {
        S.selectMode = Boolean(enabled);
        if (!S.selectMode) S.selectedIds.clear();
        $("selectModeBtn").classList.toggle("is-active", S.selectMode);
        $("selectionBar").hidden = !S.selectMode;
        renderMessages();
        updateSelectionBar();
    }

    function updateSelectionBar() {
        var count = S.selectedIds ? S.selectedIds.size : 0;
        $("selectionCount").textContent = "已选 " + count + " 条";
        $("batchDeleteBtn").disabled = count === 0;
    }

    function toggleMessageSelection(item) {
        if (!item || !item.msg_id_client) return;
        if (S.selectedIds.has(item.msg_id_client)) {
            S.selectedIds.delete(item.msg_id_client);
        } else {
            S.selectedIds.add(item.msg_id_client);
        }
        var wrappers = document.querySelectorAll(".rm-msg[data-msg-id]");
        Array.prototype.forEach.call(wrappers, function (wrapper) {
            if (wrapper.dataset.msgId !== item.msg_id_client) return;
            var selected = S.selectedIds.has(item.msg_id_client);
            wrapper.classList.toggle("is-selected", selected);
            var button = wrapper.querySelector(".rm-msg-select");
            if (button) {
                button.innerHTML = selected
                    ? '<i class="fas fa-square-check"></i>'
                    : '<i class="fas fa-square"></i>';
            }
        });
        updateSelectionBar();
    }

    function selectAllCurrent() {
        S.messages.forEach(function (item) {
            if (item.msg_id_client && !item.deleted && String(item.sender_id || "") === String((S.binding || {}).account_id || "")) {
                S.selectedIds.add(item.msg_id_client);
            }
        });
        renderMessages();
        updateSelectionBar();
    }

    function looksLikeTokenError(message) {
        return /token|登录|失效|非法|invalid|401|403/i.test(String(message || ""));
    }

    function markTokenInvalid(message) {
        S.accountValid = false;
        $("tokenWarningText").textContent = "个人号 Token 已失效：" + String(message || "请重新登录");
        renderAccount();
    }

    function channelLabel() {
        if (!S.channel) return "";
        return [S.channel.member_name, S.channel.room_label, S.channel.channel_id].filter(Boolean).join(" · ");
    }

    // ── Schedule modal ─────────────────────────────────────────────────────
    function syncJitterLimit() {
        var minInterval = S.limits.min_interval || 1;
        var interval = Number($("jobInterval").value) || (S.limits.default_interval || 60);
        var maxJitter = Math.max(0, interval - minInterval);
        if ((S.limits.max_jitter || 0) > 0) {
            maxJitter = Math.min(maxJitter, S.limits.max_jitter);
        }
        $("jobJitter").max = String(maxJitter);
        if (Number($("jobJitter").value) > maxJitter) {
            $("jobJitter").value = String(maxJitter);
        }
        var hint = $("batchLimitHint");
        if (S.scheduleMode === "once") {
            hint.hidden = true;
            return;
        }
        hint.hidden = false;
        var batchText = (S.limits.max_batch || 0) > 0
            ? ("单批最多 " + S.limits.max_batch + " 条消息；")
            : "批量条数不设业务上限；";
        hint.innerHTML = batchText + "最小间隔 " + minInterval +
            " 秒。随机浮动不会让实际间隔低于 " + minInterval + " 秒（当前 ±" + maxJitter + " 秒）。";
    }

    function setScheduleMode(mode) {
        S.scheduleMode = mode;
        Array.prototype.forEach.call(document.querySelectorAll(".rm-seg-btn"), function (button) {
            button.classList.toggle("is-active", button.dataset.mode === mode);
        });
        var batch = mode !== "once";
        $("messagesLabel").textContent = batch ? "消息内容（每行一条）" : "消息内容";
        $("jobMessages").rows = batch ? 7 : 4;
        $("jobMessages").placeholder = batch ? "每行一条消息，按顺序发送" : "输入要定时发送的消息";
        $("intervalField").hidden = !batch;
        $("jitterField").hidden = !batch;
        $("dailyHint").hidden = mode !== "daily";
        $("jobConfirmText").textContent = batch
            ? "我已确认目标频道、消息内容和发送间隔"
            : "我已确认目标频道和消息内容";
        $("schedulePreview").textContent = "";
        syncJitterLimit();
    }

    function openEditJob(job) {
        if (!job) return;
        S.editingJobId = job.id;
        $("scheduleModalTitle").innerHTML = '<i class="fas fa-pen"></i> 编辑发送计划';
        $("createJobBtn").innerHTML = '<i class="fas fa-floppy-disk"></i> 保存修改';
        $("scheduleTarget").textContent = "目标频道：" + [
            job.channel && job.channel.member_name,
            job.channel && job.channel.room_label,
            job.channel && job.channel.channel_id
        ].filter(Boolean).join(" · ");
        var mode = job.repeat_daily ? "daily" : (job.mode === "batch" ? "batch" : "once");
        setScheduleMode(mode);
        var messages = (job.messages || []).map(function (item) { return item.text || ""; });
        $("jobMessages").value = messages.join("\n");
        $("jobInterval").value = job.interval_seconds || S.limits.default_interval || 60;
        $("jobJitter").value = job.jitter_seconds || 0;
        var startMs = Number(job.next_run_at || 0) * 1000;
        if (!startMs || startMs < Date.now()) startMs = Date.now() + 5 * 60 * 1000;
        $("jobStartAt").value = localInputValue(new Date(startMs));
        $("jobConfirm").checked = false;
        $("schedulePreview").textContent = "";
        showError($("scheduleError"), "");
        syncJitterLimit();
        openModal("scheduleModal");
        track("admin_modal", { page: "room_messenger", action: "edit_job" });
    }

    function openScheduleModal() {
        if (!S.channel || !S.binding) return;
        S.editingJobId = null;
        $("scheduleModalTitle").innerHTML = '<i class="fas fa-calendar-clock"></i> 定时 / 批量发送';
        $("createJobBtn").innerHTML = '<i class="fas fa-play"></i> 创建任务';
        $("scheduleTarget").textContent = "目标频道：" + channelLabel();
        setScheduleMode("once");
        var start = new Date(Date.now() + 5 * 60 * 1000);
        $("jobStartAt").value = localInputValue(start);
        $("jobInterval").value = S.limits.default_interval || 60;
        $("jobInterval").min = String(S.limits.min_interval || 1);
        $("jobJitter").value = "10";
        $("jobJitter").max = "";
        syncJitterLimit();
        $("jobMessages").value = $("messageInput").value || "";
        $("jobConfirm").checked = false;
        $("schedulePreview").textContent = "";
        showError($("scheduleError"), "");
        openModal("scheduleModal");
        track("admin_modal", { page: "room_messenger", action: "schedule_open" });
    }

    function jobMessages() {
        var mode = S.scheduleMode;
        var raw = $("jobMessages").value;
        if (mode === "once") {
            var single = raw.trim();
            return single ? [single] : [];
        }
        return raw.split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean);
    }

    function buildSchedulePreview() {
        var messages = jobMessages();
        var startValue = $("jobStartAt").value;
        if (!messages.length) return { error: "请填写至少一条消息" };
        if (!startValue) return { error: "请选择开始时间" };
        var start = new Date(toShanghaiIso(startValue));
        if (isNaN(start.getTime())) return { error: "开始时间无效" };
        var interval = withDefault(Number($("jobInterval").value), S.limits.default_interval || 60);
        var jitter = withDefault(Number($("jobJitter").value), 0);
        var minInterval = S.limits.min_interval || 1;
        jitter = Math.min(jitter, Math.max(0, interval - minInterval));
        if ((S.limits.max_batch || 0) > 0 && messages.length > S.limits.max_batch) {
            return { error: "最多 " + S.limits.max_batch + " 条消息" };
        }
        if (S.scheduleMode !== "once" && interval < minInterval) {
            return { error: "发送间隔不能小于 " + minInterval + " 秒" };
        }
        var lines = [];
        messages.slice(0, 12).forEach(function (text, index) {
            var at = new Date(start.getTime() + index * interval * 1000);
            lines.push((index + 1) + ". " + formatDateTime(at.getTime() / 1000) + "  " + text);
        });
        if (messages.length > 12) lines.push("… 其余 " + (messages.length - 12) + " 条按间隔继续");
        return {
            messages: messages,
            start: start,
            interval: interval,
            jitter: jitter,
            text: "共 " + messages.length + " 条 · " + (S.scheduleMode === "daily" ? "每日重复" : "单次计划") +
                "\n首条：" + formatDateTime(start.getTime() / 1000) +
                (S.scheduleMode !== "once" ? "\n间隔：" + interval + " 秒" + (jitter ? "（±" + jitter + " 秒）" : "") : "") +
                "\n\n" + lines.join("\n")
        };
    }

    function withDefault(value, fallback) {
        return Number.isFinite(value) && value > 0 ? value : fallback;
    }

    function previewJob() {
        var preview = buildSchedulePreview();
        if (preview.error) {
            showError($("scheduleError"), preview.error);
            $("schedulePreview").textContent = "";
            return;
        }
        showError($("scheduleError"), "");
        $("schedulePreview").textContent = preview.text;
    }

    function createJob() {
        if (!$("jobConfirm").checked) {
            showError($("scheduleError"), "请先勾选确认");
            return;
        }
        var preview = buildSchedulePreview();
        if (preview.error) {
            showError($("scheduleError"), preview.error);
            return;
        }
        var button = $("createJobBtn");
        button.disabled = true;
        showError($("scheduleError"), "");
        var editingJobId = S.editingJobId;
        var body = {
            messages: preview.messages,
            interval_seconds: preview.interval,
            jitter_seconds: preview.jitter,
            start_at: toShanghaiIso($("jobStartAt").value),
            repeat_daily: S.scheduleMode === "daily",
            confirm: true
        };
        if (!editingJobId) body.channel = S.channel;
        api(editingJobId ? ("/jobs/" + encodeURIComponent(editingJobId) + "/edit") : "/jobs", {
            method: "POST",
            body: body
        }).then(function () {
            closeModal("scheduleModal");
            toast(editingJobId ? "发送计划已保存" : "发送计划已创建", "success");
            track("admin_update", {
                page: "room_messenger",
                action: editingJobId ? "edit_job" : "create_job",
                mode: S.scheduleMode,
                total: preview.messages.length
            });
            S.editingJobId = null;
            loadJobs();
            openQueue();
        }).catch(function (error) {
            showError($("scheduleError"), error.message);
        }).finally(function () {
            button.disabled = false;
        });
    }

    // ── Jobs ───────────────────────────────────────────────────────────────
    var STATUS_LABELS = {
        scheduled: "等待中",
        running: "发送中",
        paused: "已暂停",
        completed: "已完成",
        failed: "失败",
        cancelled: "已取消"
    };
    var MSG_STATUS_LABELS = {
        pending: "待发送",
        sending: "发送中",
        sent: "已发送",
        failed: "失败",
        unknown: "结果未知",
        cancelled: "已取消"
    };

    function setQueueTab(tab) {
        S.queueTab = tab;
        Array.prototype.forEach.call(document.querySelectorAll(".rm-queue-tab"), function (button) {
            button.classList.toggle("is-active", button.dataset.qtab === tab);
        });
        $("jobList").hidden = tab !== "jobs";
        $("sentLogList").hidden = tab !== "log";
        $("sentLogFilters").hidden = tab !== "log";
        if (tab === "log") loadSentLog();
    }

    function loadSentLog() {
        return api("/sent-log?limit=80").then(function (data) {
            S.sentLog = Array.isArray(data.entries) ? data.entries : [];
            renderSentLog();
        }).catch(function (error) {
            if (S.verified) toast(error.message || "读取发送记录失败", "error");
        });
    }

    function renderSentLog() {
        var wrap = $("sentLogList");
        var query = $("sentLogQuery").value.trim().toLowerCase();
        var status = $("sentLogStatus").value;
        var date = $("sentLogDate").value;
        var rows = S.sentLog.filter(function (entry) {
            if (status && entry.status !== status) return false;
            if (date && String(entry.at || "").slice(0, 10) !== date) return false;
            if (query) {
                var haystack = [entry.member_name, entry.room_label, entry.channel_id, entry.text].join(" ").toLowerCase();
                if (haystack.indexOf(query) < 0) return false;
            }
            return true;
        });
        if (!rows.length) {
            wrap.innerHTML = '<div class="rm-empty-small">' + (S.sentLog.length ? "没有匹配的发送记录" : "暂无发送记录") + '</div>';
            return;
        }
        wrap.innerHTML = "";
        rows.forEach(function (entry) {
            var card = document.createElement("div");
            card.className = "rm-sent-card" + (entry.status === "failed" ? " is-failed" : "");
            var channel = [entry.member_name, entry.room_label].filter(Boolean).join(" · ") || ("频道 " + (entry.channel_id || ""));
            var source = entry.source === "job" ? "定时/批量" : "即时";
            var status = entry.status === "sent" ? "已发送" : "发送失败";
            card.innerHTML =
                '<div class="rm-sent-top"><span class="rm-sent-channel">' + escapeHtml(channel) + '</span>' +
                '<span class="rm-sent-time">' + escapeHtml(formatIso(entry.at)) + '</span></div>' +
                '<div class="rm-sent-meta"><span>' + escapeHtml(source) + '</span><span>·</span><span>' +
                escapeHtml(status) + '</span>' + (entry.error ? '<span>·</span><span>' + escapeHtml(entry.error) + '</span>' : "") + '</div>' +
                '<div class="rm-sent-text">' + escapeHtml(entry.text || "") + '</div>';
            wrap.appendChild(card);
        });
    }

    function checkJobAlerts() {
        var bad = S.jobs.find(function (job) {
            return (job.status === "failed" || job.status === "paused") && job.last_error;
        });
        if (!bad) {
            $("globalAlert").hidden = true;
            return;
        }
        var key = [bad.id, bad.status, bad.last_error, bad.updated_at].join("|");
        if (key === S.dismissedAlertKey) {
            $("globalAlert").hidden = true;
            return;
        }
        var label = [bad.channel && bad.channel.member_name, bad.channel && bad.channel.room_label].filter(Boolean).join(" · ") || "发送任务";
        var text = label + "：" + bad.last_error;
        $("globalAlertText").textContent = text;
        $("globalAlert").hidden = false;
        if (key !== S.lastAlertKey && typeof Notification !== "undefined" && Notification.permission === "granted") {
            try {
                new Notification("房间信使任务异常", { body: text.slice(0, 180) });
            } catch (error) { /* notification is best effort */ }
        }
        S.lastAlertKey = key;
    }

    function loadJobs() {
        return api("/jobs").then(function (data) {
            S.jobs = Array.isArray(data.jobs) ? data.jobs : [];
            if (data.limits) S.limits = data.limits;
            if (typeof data.daily_sent === "number") {
                S.dailySent = data.daily_sent;
                renderDailyMeter();
            }
            renderJobs();
            updateQueueBadge();
            checkJobAlerts();
        }).catch(function () { /* quiet */ });
    }

    function updateQueueBadge() {
        var active = S.jobs.filter(function (job) {
            return ["scheduled", "running", "paused"].indexOf(job.status) >= 0;
        }).length;
        var badge = $("queueBadge");
        badge.textContent = String(active);
        badge.hidden = !active;
    }

    function renderJobs() {
        var wrap = $("jobList");
        if (!S.jobs.length) {
            wrap.innerHTML = '<div class="rm-empty-small">暂无发送计划</div>';
            return;
        }
        wrap.innerHTML = "";
        S.jobs.forEach(function (job) {
            var card = document.createElement("div");
            card.className = "rm-job-card";
            var channel = job.channel || {};
            var label = [channel.member_name, channel.room_label].filter(Boolean).join(" · ") || ("频道 " + (channel.channel_id || ""));
            var percent = job.total ? Math.round((job.sent / job.total) * 100) : 0;
            var statusClass = job.status || "scheduled";
            card.innerHTML =
                '<div class="rm-job-top"><div class="rm-job-title">' + escapeHtml(label) +
                '<div class="rm-job-sub">' + escapeHtml(modeLabel(job)) + ' · ' + job.sent + '/' + job.total +
                (job.next_run_label ? ' · 下次 ' + escapeHtml(job.next_run_label) : '') + '</div></div>' +
                '<span class="rm-status ' + escapeHtml(statusClass) + '">' + escapeHtml(STATUS_LABELS[job.status] || job.status) + '</span></div>' +
                '<div class="rm-progress"><span style="width:' + percent + '%"></span></div>' +
                (job.last_error ? '<div class="rm-form-error" style="margin:6px 0 0">' + escapeHtml(job.last_error) + '</div>' : "") +
                '<div class="rm-job-actions"></div>';
            var actions = card.querySelector(".rm-job-actions");
            var editable = ["scheduled", "paused"].indexOf(job.status) >= 0 &&
                (job.messages || []).every(function (item) {
                    return item.status === "pending" || item.status === "failed";
                });
            if (editable) {
                var editButton = document.createElement("button");
                editButton.type = "button";
                editButton.className = "rm-btn rm-btn-small";
                editButton.textContent = "编辑";
                editButton.addEventListener("click", function () { openEditJob(job); });
                actions.appendChild(editButton);
            }
            if (job.status === "scheduled" || job.status === "running") {
                actions.appendChild(jobActionButton("暂停", "pause", job, "fa-pause"));
            }
            if (job.status === "paused" || job.status === "failed") {
                actions.appendChild(jobActionButton("继续", "resume", job, "fa-play"));
            }
            if (["completed", "cancelled"].indexOf(job.status) < 0) {
                actions.appendChild(jobActionButton("取消", "cancel", job, "fa-ban"));
            }
            var detailButton = document.createElement("button");
            detailButton.type = "button";
            detailButton.className = "rm-btn rm-btn-small rm-btn-ghost";
            detailButton.innerHTML = '<i class="fas fa-chevron-down"></i> 详情';
            actions.appendChild(detailButton);
            var detail = document.createElement("div");
            detail.className = "rm-job-detail";
            detail.hidden = true;
            detail.innerHTML = (job.messages || []).map(function (item) {
                return '<div class="rm-job-msg"><span class="rm-msg-state ' + escapeHtml(item.status) + '">' +
                    escapeHtml(MSG_STATUS_LABELS[item.status] || item.status) + '</span>' +
                    '<span class="rm-job-msg-text">' + escapeHtml(item.text) +
                    (item.error ? ' <span style="color:#fca5a5">（' + escapeHtml(item.error) + '）</span>' : "") +
                    '</span></div>';
            }).join("");
            detailButton.addEventListener("click", function () {
                detail.hidden = !detail.hidden;
                detailButton.innerHTML = detail.hidden
                    ? '<i class="fas fa-chevron-down"></i> 详情'
                    : '<i class="fas fa-chevron-up"></i> 收起';
            });
            card.appendChild(detail);
            wrap.appendChild(card);
        });
    }

    function modeLabel(job) {
        if (job.repeat_daily) return "每日 " + (job.interval_seconds || 0) + "s 间隔";
        if (job.mode === "batch") return "批量 " + (job.interval_seconds || 0) + "s 间隔";
        return "单次定时";
    }

    function jobActionButton(label, action, job, icon) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "rm-btn rm-btn-small" + (action === "cancel" ? " rm-btn-ghost" : "");
        button.innerHTML = '<i class="fas ' + icon + '"></i> ' + label;
        button.addEventListener("click", function () {
            if (action === "cancel" && !window.confirm("确定取消这个发送计划？已发送的消息不会撤回。")) return;
            api("/jobs/" + encodeURIComponent(job.id) + "/" + action, { method: "POST", body: {} })
                .then(function () {
                    toast("操作已提交", "success");
                    loadJobs();
                    track("admin_update", { page: "room_messenger", action: "job_" + action });
                })
                .catch(function (error) { toast(error.message, "error"); });
        });
        return button;
    }

    function startJobsPolling() {
        clearInterval(S.jobsTimer);
        S.jobsTimer = setInterval(function () {
            if (document.hidden) return;
            loadJobs();
        }, 5000);
    }

    function stopTimers() {
        stopPolling();
        clearInterval(S.jobsTimer);
        S.jobsTimer = null;
    }

    // ── Modals / drawer ────────────────────────────────────────────────────
    function openModal(id) {
        $(id).hidden = false;
        document.body.style.overflow = "hidden";
    }

    function closeModal(id) {
        $(id).hidden = true;
        if (!document.querySelector(".rm-modal:not([hidden])")) {
            document.body.style.overflow = "";
        }
    }

    function openQueue() {
        S.jobsOpen = true;
        $("app").classList.add("queue-open");
        $("queuePanel").hidden = false;
        loadJobs();
        setQueueTab(S.queueTab || "jobs");
    }

    function closeQueue() {
        S.jobsOpen = false;
        $("app").classList.remove("queue-open");
        $("queuePanel").hidden = true;
    }

    function openSidebar() {
        $("sidebar").classList.add("is-open");
        $("sidebarBackdrop").hidden = false;
    }

    function closeSidebar() {
        $("sidebar").classList.remove("is-open");
        $("sidebarBackdrop").hidden = true;
    }

    // ── Events ─────────────────────────────────────────────────────────────
    function bindEvents() {
        $("loginForm").addEventListener("submit", login);
        $("accountForm").addEventListener("submit", function (event) { event.preventDefault(); });
        $("logoutBtn").addEventListener("click", logoutPage);
        $("accountLoginBtn").addEventListener("click", openAccountModal);
        $("tokenReloginBtn").addEventListener("click", openAccountModal);
        $("accountProbeBtn").addEventListener("click", function () { probeAccount(false); });
        $("accountUnbindBtn").addEventListener("click", unbindAccount);
        $("smsBtn").addEventListener("click", sendSms);
        $("securityBtn").addEventListener("click", submitSecurity);
        $("verifyBtn").addEventListener("click", verifyCode);

        Array.prototype.forEach.call(document.querySelectorAll(".rm-tab"), function (button) {
            button.addEventListener("click", function () { setTab(button.dataset.tab); });
        });
        $("channelSearch").addEventListener("input", function () {
            if (S.tab === "recent") {
                renderRecent();
            } else {
                clearTimeout(S.searchTimer);
                S.searchTimer = setTimeout(function () { loadCatalog(true); }, 300);
            }
        });

        $("sidebarOpen").addEventListener("click", openSidebar);
        $("sidebarClose").addEventListener("click", closeSidebar);
        $("sidebarBackdrop").addEventListener("click", closeSidebar);
        $("selectModeBtn").addEventListener("click", function () { setSelectMode(!S.selectMode); });
        $("selectAllBtn").addEventListener("click", selectAllCurrent);
        $("batchDeleteBtn").addEventListener("click", openBatchDeleteModal);
        $("cancelSelectBtn").addEventListener("click", function () { setSelectMode(false); });
        $("refreshBtn").addEventListener("click", function () {
            if (!S.channel) return;
            initialLoad();
            loadJobs();
            toast("正在刷新", "success");
        });
        $("queueBtn").addEventListener("click", openQueue);
        $("queueClose").addEventListener("click", closeQueue);
        $("globalAlertQueueBtn").addEventListener("click", openQueue);
        $("globalAlertClose").addEventListener("click", function () {
            S.dismissedAlertKey = S.lastAlertKey;
            $("globalAlert").hidden = true;
        });
        $("enableNotifyBtn").addEventListener("click", function () {
            if (typeof Notification === "undefined") {
                toast("当前浏览器不支持桌面通知", "error");
                return;
            }
            try {
                Notification.requestPermission().then(function (permission) {
                    toast(permission === "granted" ? "已开启任务异常通知" : "未获得通知权限", permission === "granted" ? "success" : "error");
                }).catch(function () { toast("未获得通知权限", "error"); });
            } catch (error) {
                toast("当前浏览器不支持桌面通知", "error");
            }
        });
        Array.prototype.forEach.call(document.querySelectorAll(".rm-queue-tab"), function (button) {
            button.addEventListener("click", function () { setQueueTab(button.dataset.qtab); });
        });
        $("sentLogQuery").addEventListener("input", renderSentLog);
        $("sentLogStatus").addEventListener("change", renderSentLog);
        $("sentLogDate").addEventListener("change", renderSentLog);
        $("jumpLatest").addEventListener("click", function () { scrollToBottom(true); });

        $("chat").addEventListener("scroll", function () {
            var chat = $("chat");
            S.nearBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 120;
            $("jumpLatest").hidden = S.nearBottom || !S.messages.length;
        });

        $("messageInput").addEventListener("input", autoResizeComposer);
        $("messageInput").addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
                event.preventDefault();
                openSendModal();
            }
        });
        $("sendBtn").addEventListener("click", openSendModal);
        $("scheduleBtn").addEventListener("click", openScheduleModal);
        $("confirmSendBtn").addEventListener("click", confirmSend);
        $("confirmWordInput").addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                confirmSend();
            }
        });
        $("confirmDeleteBtn").addEventListener("click", confirmDelete);
        $("deleteConfirmWordInput").addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
                confirmDelete();
            }
        });

        Array.prototype.forEach.call(document.querySelectorAll(".rm-seg-btn"), function (button) {
            button.addEventListener("click", function () { setScheduleMode(button.dataset.mode); });
        });
        $("jobInterval").addEventListener("input", syncJitterLimit);
        $("previewJobBtn").addEventListener("click", previewJob);
        $("createJobBtn").addEventListener("click", createJob);

        Array.prototype.forEach.call(document.querySelectorAll("[data-close]"), function (button) {
            button.addEventListener("click", function () { closeModal(button.dataset.close); });
        });
        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") return;
            var openModalEl = document.querySelector(".rm-modal:not([hidden])");
            if (openModalEl) {
                closeModal(openModalEl.id);
                return;
            }
            if (S.jobsOpen) {
                closeQueue();
                return;
            }
            if (S.selectMode) {
                setSelectMode(false);
                return;
            }
            closeSidebar();
        });
        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                stopPolling();
            } else if (S.channel) {
                pollMessages();
                startPolling();
            }
        });
    }

    var initialized = false;

    function init() {
        if (initialized) return;
        if (!document.getElementById("loginForm")) {
            setTimeout(init, 300);
            return;
        }
        initialized = true;
        bindEvents();
        autoResizeComposer();
        renderDailyMeter();
        setScheduleMode("once");
        boot();
    }

    // Safari 偶发把 DOMContentLoaded 拖到很晚；保留一个兜底，确保按钮能绑定。
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
        setTimeout(init, 1200);
    } else {
        init();
    }
})();
