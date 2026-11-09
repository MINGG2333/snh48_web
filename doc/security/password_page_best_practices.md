# 密码保护页面与后台鉴权最佳实践

> 更新日期：2026-11-09
>
> 适用范围：本仓库所有带访问密码的页面、管理后台、写入 API 和异步任务入口。
>
> 强制要求：新增或修改密码页、登录接口、Cookie/Token 会话前，先读本文；先按第 1 节选定模式，再按对应模式实现和验收。

## 1. 结论先行：先选模式

本站密码页有**三种模式**，不是所有页面都必须用 Cookie。选错模式会导致“该重输的时候不重输”或“不该重输的时候反复重输”。

| 模式 | 会话存放位置 | F5 后 | 网站重启后 | 适用页面 |
|---|---|---|---|---|
| **A. HttpOnly Cookie（60 分钟）** | 服务端签名 Cookie；签名密钥在进程内存 | 60 分钟内免密 | 必须重输 | 高频查看、需要长期停留、带导出/轮询的管理页 |
| **B. 页面内存密码（请求头）** | 仅当前页面 JS 变量 | 必须重输 | 必须重输 | 低频或高敏感页面、希望每次打开都验证、页面无媒体元素 |
| **C. 页面内存密码 + 媒体签名 URL** | 仅当前页面 JS 变量 | 必须重输 | 必须重输 | 同 B，但页面含 `<audio>`/`<video>` 等无法带请求头的受保护资源 |

### 1.1 选择顺序

1. **这个页面是否必须“F5 后重新输密码”？**
   - 否 → 选 **模式 A**（默认，体验最好，适合高频页面）。
   - 是 → 选 **模式 B 或 C**。
2. 选 B/C 后：**页面是否包含只能靠 URL 加载的受保护资源**（`<audio>`、`<video>`、图片等）？
   - 是 → 选 **模式 C**（短时签名 URL）。
   - 否 → 选 **模式 B**（普通请求头密码）。

### 1.2 当前页面归属（2026-11-09）

- **模式 A**：`/radio`（上麦回放）、`/business/redblue2026`、`/weidian-orders`、`/social-credentials-admin`、`/scroller-admin`、`/room/messenger`（房间信使）
- **模式 B**：`/room`（房间消息）、`/gift-replies`、计分页、`/business-admin`、`/ob`、记忆页、QA
- **模式 C**：`/flip`、`/flip-cards`

### 1.3 三种模式的共同底线

1. **密码只用于验证，浏览器持久层不保存明文密码**；禁止写入 `localStorage`、`sessionStorage`、IndexedDB、JS 可读 Cookie 或 URL。
2. **旧/未知会话必须按“登录已过期”返回 401**，不能返回 403“密码错误”，也不得计入密码失败限流；只有真正提交了密码（`/login` 或密码请求头）才计一次失败。
3. **每个密码组使用独立限流预算**，不要和观察页或其他页面共用。
4. **页面壳可以为公开 HTML，但每个数据/写入 API 必须独立鉴权**，不能只靠前端隐藏页面。
5. **`/verify` 只做轻量鉴权检查**，不返回业务数据，并设置 `Cache-Control: no-store`。
6. **禁止**在密码输入框使用 `autocomplete="current-password"`；统一使用 `autocomplete="new-password"`。
7. **模式 B/C 的页面必须提供页面内“刷新数据”按钮**，让用户刷新内容时不必按 F5 重输密码。

---

### 1.4 新增密码页的密码来源（2026-11-09 用户定）

- 不要为一个新页面自行发明一套新密码。
- 正确做法：为该页声明独立环境变量（如 `ROOM_MESSENGER_PASSWORD`），**默认留空**；为空时复用最接近的业务页密码。
- 当前映射：
  - `/room/messenger` → `ROOM_MESSENGER_PASSWORD`，为空复用 `SCORE_GIFTS_PASSWORD`，再回退 `GIFT_REPLIES_PASSWORD`；
  - 其他新页面按同样方式选择语义最接近的现有密码组，并在 `.env.example` 和本文登记。
- 只有确实需要隔离风险时，才由 owner 显式填写该页面的独立密码；代码和部署流程不得自动生成或写入新密码。

## 2. 模式 A：HttpOnly Cookie（60 分钟）

### 2.1 登录流程

```text
浏览器                         服务端
  |  POST /api/xxx/login          |
  |  {"password": "..."}         |
  |----------------------------->|
  |                              | compare_digest(密码, 环境变量)
  |                              | Set-Cookie: xxx_auth=<HMAC token>
  |                              | HttpOnly; Secure; SameSite=Strict; Path=/api/xxx
  |<-----------------------------|
  |  GET /api/xxx/verify          |
  |  Cookie: xxx_auth=...        |
  |----------------------------->|
  |<-----------------------------| 200 {"verified": true}
  |  GET /api/xxx/data           |
  |  Cookie: xxx_auth=...        |
  |----------------------------->|
  |<-----------------------------| 业务数据
```

Cookie 的 `Path` 必须限定到该功能的 API 前缀，例如 `/api/redblue`，不要使用 `/`。Cookie 的值必须是服务端生成的 HMAC token，不能是密码本身，也不能是可逆编码。

### 2.2 服务端常量与 token

```python
from website import password_session

AUTH_COOKIE = "xxx_auth"
AUTH_COOKIE_MAX_AGE = password_session.cookie_max_age()  # 默认 60 分钟


def _cookie_token(password: str) -> str:
    return password_session.cookie_token(password, context="xxx")
```

- 统一走 `website/password_session.py`，不要在页面里各写一套。
- Cookie 有效期由 `PASSWORD_SESSION_MAX_AGE_SECONDS` 控制（默认 3600 秒；想更严格可设 1800）。
- 签名密钥只在进程内存中（`password_session.COOKIE_SECRET`），网站重启后旧 Cookie 全部失效、页面回到登录页；这是有意为之，不落盘密钥。
- 旧实现中红蓝台账的持久密钥文件（`private_handover/web_state/redblue_ledger_cookie_secret`）已于 2026-11-09 停用，并移入 `private_handover/存档/停用密钥/`（附 README 说明）；`private_handover/web_state/` 下不应再出现该文件，不得再把它接回代码或 `.env`。如果部署后发现该文件重新出现，说明有旧代码被回退，应立即检查 `website/redblue_ledger_api.py` 是否仍引用 `REDBLUE_COOKIE_SECRET_PATH`，并把新生成的文件再次归档。
- 如果未来改成多 worker，必须把 `password_session.COOKIE_SECRET` 改为所有 worker 共享的密钥（环境变量），否则不同 worker 签发的 Cookie 会互相失效；这不改变“重启失效”的策略。

### 2.3 鉴权依赖

```python
def verify_xxx_password(
    request: Request,
    x_xxx_password: str = Header(None, alias="X-Xxx-Password"),
    xxx_auth: str = Cookie(None, alias=AUTH_COOKIE),
):
    expected = cfg.XXX_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="功能未启用")
    if password_session.cookie_matches(xxx_auth, expected, context="xxx"):
        return True
    if x_xxx_password and hmac.compare_digest(x_xxx_password, expected):
        return True
    if not password_session.password_was_submitted(x_xxx_password):
        # 缺密码或旧/未知 Cookie：登录已过期，不计数
        raise HTTPException(status_code=401, detail="需要密码")
    check_login_limit(request)  # 只有真正提交了错误密码才计数
    raise HTTPException(status_code=403, detail="密码错误")
```

- Cookie 优先，请求头密码只作为旧客户端/测试兼容入口；模式 A 的新前端不得再发送密码请求头。
- 未配置密码时返回 403，不能降级为公开访问。
- 失败尝试必须限速；成功登录和旧 Cookie 不应消耗失败额度。

### 2.4 登录与登出

```python
@router.post("/login")
def login(payload: LoginRequest, response: Response, request: Request):
    expected = cfg.XXX_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="功能未启用")
    if not hmac.compare_digest(payload.password, expected):
        check_login_limit(request)
        raise HTTPException(status_code=403, detail="密码错误")
    response.set_cookie(
        key=AUTH_COOKIE,
        value=password_session.cookie_token(expected, context="xxx"),
        max_age=password_session.cookie_max_age(),
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
        path="/api/xxx",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE,
        path="/api/xxx",
        httponly=True,
        secure=cfg.SECURE_COOKIES,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"success": True}
```

- `Secure` 由 `cfg.SECURE_COOKIES` 控制；生产 HTTPS 必须为 true。
- `SameSite=Strict` 是默认要求；写入类接口如涉及高风险操作，再增加 `Origin`/`Host` 同源校验。
- 登出必须调用服务端接口删除 HttpOnly Cookie；前端无法直接清除 HttpOnly Cookie。
- 登录、登出、`/verify` 和业务响应都应设置 `Cache-Control: no-store`。

### 2.5 前端实现

登录：

```javascript
const response = await fetch("/api/xxx/login", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({password: value}),
  credentials: "same-origin",
  cache: "no-store",
});
if (!response.ok) throw new Error("密码错误");
passwordInput.value = "";
showApp();
```

启动检查：

```javascript
async function boot() {
  let verified = false;
  try {
    const response = await fetch("/api/xxx/verify", {
      credentials: "same-origin",
      cache: "no-store",
    });
    verified = response.ok;
  } catch (error) {}
  if (!verified) {
    showLogin("");
    return;
  }
  showApp();
  await loadData();
}
```

业务请求与失效处理：

```javascript
async function api(path, options) {
  options = options || {};
  options.credentials = "same-origin";
  options.cache = "no-store";
  const response = await fetch(path, options);
  if (response.status === 401 || response.status === 403) {
    showLogin("登录已失效，请重新输入密码");
    throw new Error("登录已失效，请重新输入密码");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}
```

- 所有同源 API 请求统一带 `credentials: "same-origin"`。
- 见到 401/403 统一回到登录态，不要在多个轮询/导出函数里各自处理。
- 除登录态失效外的加载错误应提示“重试加载”，不要误报“密码错误”。
- 导出、下载、轮询、自动同步也必须走同一套 Cookie 鉴权。

---

## 3. 模式 B：页面内存密码（请求头）

适用于“希望 F5/重新打开页面必须重输密码”、且页面没有受保护媒体元素的页面。密码只存在当前页面的 JS 变量中，不写任何浏览器持久层。

### 3.1 服务端

```python
async def verify_xxx_password(
    request: Request,
    x_xxx_password: str = Header(None, alias="X-Xxx-Password"),
):
    expected = cfg.XXX_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="功能未启用")
    if not x_xxx_password:
        raise HTTPException(status_code=401, detail="需要密码")
    if hmac.compare_digest(x_xxx_password, expected):
        return True
    check_xxx_login_limit(get_client_ip(request), "密码尝试过于频繁，请稍后再试")
    raise HTTPException(status_code=403, detail="密码错误")
```

- 不需要 `/login` 下发 Cookie；可以保留一个只校验、不 `Set-Cookie` 的 `/login` 或 `/verify`。
- 缺请求头 → 401，不计数；错误请求头 → 403，计数。
- 每个页面组使用自己的限流器，例如 `check_room_messages_login_limit`，不要共用观察页预算。

### 3.2 前端

```javascript
var password = "";  // 仅页面内存，不要挂到 window

async function api(path, options) {
  options = options || {};
  options.credentials = "same-origin";
  options.cache = "no-store";
  if (password) {
    options.headers = Object.assign(
      {"X-Xxx-Password": password},
      options.headers || {}
    );
  }
  const response = await fetch(path, options);
  if (response.status === 401) {
    resetLogin("登录已失效，请重新输入密码");
    throw new Error("登录已失效，请重新输入密码");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

// 启动：不自动登录，直接显示密码框（F5 后内存已清空）
showLogin("");

// 登录：带请求头调用 /verify 或轻量接口，成功后把密码留在内存
async function login(value) {
  password = value;
  await api("/verify");  // 失败时清空 password 并回到密码框
  showApp();
  await loadData();
}
```

- 登录成功后清空输入框，但密码变量保留在内存，供页面内请求使用。
- **必须提供页面内“刷新数据”按钮**，刷新内容时不需要重输密码。
- 401 自动回到密码框；403 只在登录表单显示“密码错误”。
- 禁止把密码写入 Web Storage；变量不要挂到 `window`。

当前实现参考：`website/templates/room_messages.html`、`website/room_messages_api.py`。

---

## 4. 模式 C：页面内存密码 + 媒体签名 URL

模式 B 的密码在请求头里，但 `<audio>`、`<video>`、`<img>` 等元素只能通过 URL 加载，无法携带自定义请求头。因此模式 C 在 B 的基础上，由 `/data` 返回**短时签名 URL**。

### 4.1 服务端

```python
MEDIA_TOKEN_TTL_SECONDS = 8 * 60 * 60

def _media_signature(expires_at: int) -> str:
    key = cfg.XXX_PASSWORD.encode("utf-8")
    message = f"xxx-media:{expires_at}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()

# /data 返回媒体 URL 时附加：
#   /api/xxx/media/voice.mp3?mt=<expires_at>&ms=<signature>

async def verify_media_access(request: Request, x_xxx_password: str = Header(None, alias="X-Xxx-Password")):
    if x_xxx_password and hmac.compare_digest(x_xxx_password, cfg.XXX_PASSWORD):
        return True
    if _media_token_valid(request.query_params.get("mt", ""), request.query_params.get("ms", "")):
        return True
    raise HTTPException(status_code=401, detail="需要密码")
```

- 签名 URL 只用于受保护媒体，不能用于数据/写入接口。
- 令牌必须短时（建议 1–8 小时），并校验过期时间和 HMAC；过期后由页面内“刷新数据”重新签发。
- 媒体接口仍保留请求头校验，便于命令行/测试。
- 旧 Cookie 不再识别；带旧 Cookie 的请求按“未登录”返回 401，不计入限流。

### 4.2 前端

- 密码只存内存变量，所有 JSON 请求带请求头。
- 媒体元素的 `src` 直接使用 `/data` 返回的签名 URL；不要在 URL 里放密码本身。
- F5 后密码和签名 URL 都失效，回到密码框。

当前实现参考：`website/flip_cards_api.py`、`website/templates/flip_cards.html`。

---

## 5. 测试清单

按模式选择对应测试；三种模式共同的静态护栏都要跑 `tests/test_password_page_security.py`。

### 5.1 模式 A

1. **登录成功**：`POST /login` 返回 200，`Set-Cookie` 包含 `HttpOnly`、`Secure`、`SameSite=strict`、正确 `Path`、`Max-Age=3600`。
2. **Cookie 鉴权**：带 Cookie 访问 `/verify`、数据接口、导出接口均成功。
3. **登出**：`POST /logout` 后数据接口返回 401。
4. **错误密码**：返回 403，不种 Cookie。
5. **旧/未知 Cookie**：返回 401，不是 403；连续 12 次不触发 429。
6. **线上烟测**：未登录 401、登录 200、带 Cookie 数据/导出 200、登出后 401。

### 5.2 模式 B

1. **无密码**：未带请求头访问数据接口返回 401，且不计入失败限流。
2. **错误密码**：错误请求头返回 403，并消耗失败限流。
3. **正确密码**：正确请求头返回 200。
4. **F5 行为**：页面启动不自动登录，直接显示密码框。
5. **页面内刷新**：不重新输入密码也能刷新数据。
6. **静态护栏**：不得出现密码写入 `localStorage`/`sessionStorage`。

### 5.3 模式 C

1. 继承模式 B 的 1–6 项。
2. **媒体无请求头可播放**：`/data` 返回的签名 URL 在不带请求头时返回 200/206（Range）。
3. **签名篡改/过期**：返回 401。
4. **签名范围**：签名 URL 只对媒体接口有效，不能用它访问数据/写入接口。

线上烟测示例（不要把真实密码写进命令历史，改为从配置读取）：

```python
import requests
from website import config as cfg

s = requests.Session()
r = s.post("https://example.com/api/xxx/login", json={"password": cfg.XXX_PASSWORD}, timeout=15)
assert r.status_code == 200
assert "HttpOnly" in r.headers.get("set-cookie", "")
assert s.get("https://example.com/api/xxx/data", timeout=15).status_code == 200
assert s.post("https://example.com/api/xxx/logout", timeout=15).status_code == 200
assert s.get("https://example.com/api/xxx/data", timeout=15).status_code == 401
```

## 6. 反模式

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 所有页面都强行改成 Cookie | 失去“F5 必须重输”的页面会变成 60 分钟免密，偏离页面定位 | 按第 1 节先选模式 |
| 用 Cookie 但把签名密钥落盘 | 登录态长期有效，部署/重启也不再强制验证 | 用 `password_session` 的内存密钥 |
| 旧/未知 Cookie 返回 403 并计入限流 | 部署后用户被误报“密码错误”，反复刷新把自己锁进 429 | 返回 401，不计数 |
| 内存密码页没有页面内刷新按钮 | 用户只能按 F5，反复重输密码 | 提供“刷新数据”按钮 |
| 受保护媒体只靠 Cookie | 改成内存密码模式后播放全部 401 | 模式 C 的签名 URL |
| `sessionStorage.setItem("xxx_password", password)` | 明文密码可被同源 JS、扩展、共享设备读取；刷新/会话恢复后继续有效 | 模式 A 的 HttpOnly Cookie，或模式 B/C 的页面内存变量 |
| `localStorage.setItem("xxx_password", password)` | 长期明文落盘，风险高于 sessionStorage | 立即迁移并清理旧 key |
| `autocomplete="current-password"` | 浏览器密码管理器可能自动保存后台密码 | `autocomplete="new-password"` |
| 页面加载时直接读取已保存密码并自动登录 | 共享浏览器标签页可无感进入后台 | 模式 A 的 Cookie 会话 + `/verify`；模式 B/C 每次重新输入 |
| 只保护页面 HTML，不保护 API | 直接请求 API 可绕过页面 | 每个数据/写入接口加鉴权依赖 |
| 把密码放 URL/query | 进入浏览器历史、代理日志、Referer | POST body 或请求头 + HTTPS（模式 C 只签媒体 URL，不放密码） |
| 登录失败不限速 | 可被暴力尝试 | 失败限速 + 通用错误信息；每个密码组独立预算 |
| Cookie `Path=/` | 同域其他页面也会携带管理 Cookie | `Path=/api/xxx` |
| 登出只清前端变量 | HttpOnly Cookie 仍有效 | 模式 A 调用服务端 `/logout` 删除 Cookie；模式 B/C 清空内存密码并回到密码框 |
| 多个页面共用同一密码 | 一处泄露影响全部后台 | 高敏感页面使用独立密码 |

## 7. 迁移与新增页面

### 7.1 新增页面

1. 按第 1 节判断用 A、B 还是 C。
2. 模式 A 按第 2 节实现；模式 B 按第 3 节；模式 C 按第 4 节。
3. 后端鉴权依赖、限流器和前端登录流程一起加，不能只加页面壳。
4. 补对应模式的测试和静态护栏。
5. 更新 `doc/website_pages.md`、`doc/security/security_baseline.md` 和运行快照。

### 7.2 存量页面

- **不要为了“统一”而批量迁移**。模式 B/C 的持久化程度低于模式 A，本身更严格；保持现状是允许的。
- 只有出现具体需求时才迁移：
  - B/C → A：用户希望 F5 不重输、页面使用频率变高，或需要长期停留的导出/轮询。
  - A → B/C：页面变得更敏感，或明确要求每次打开都验证。
- 迁移时同步修改前后端和测试，并按第 5 节重新验收。

## 8. 上线前审查清单

### 8.1 三种模式共同

- [ ] 浏览器持久层没有密码；旧 key 已清理。
- [ ] 密码框使用 `autocomplete="new-password"`。
- [ ] 密码不进 URL；只放 POST body 或请求头（模式 C 的媒体 URL 只放签名，不放密码）。
- [ ] `/verify`、业务数据、导出、轮询全部鉴权。
- [ ] 旧/未知会话返回 401“需要密码”，且不消耗密码失败限流。
- [ ] 登录失败有限速，错误信息不区分“用户不存在/密码错误”；每个密码组独立预算。
- [ ] 401 统一回登录；非鉴权错误允许重试，不误报“密码错误”。
- [ ] 单元测试、静态护栏测试、前端语法检查通过。
- [ ] `doc/website_pages.md` 和 `doc/security/security_baseline.md` 已更新。

### 8.2 模式 A 额外

- [ ] Cookie 为 `HttpOnly; Secure; SameSite=Strict; Path=/api/xxx`。
- [ ] `max_age` 使用 `password_session.cookie_max_age()`（默认 60 分钟）。
- [ ] Cookie 值是服务端 HMAC token，不是密码；签名密钥不落盘。
- [ ] 登出调用服务端接口并删除 Cookie。
- [ ] 线上未登录 401、登录 200、带 Cookie 访问 200、登出后 401。

### 8.3 模式 B/C 额外

- [ ] 页面启动不自动登录，直接显示密码框（F5 后必须重输）。
- [ ] 页面内提供“刷新数据”按钮，刷新内容不需要重输密码。
- [ ] 密码只存页面内存变量，不写 Web Storage，不挂到 `window`。
- [ ] 缺请求头返回 401 且不计数；错误请求头返回 403 并计数。
- [ ] 模式 C：签名 URL 只用于媒体、短时有效、篡改/过期返回 401。

## 9. 参考实现

- `website/password_session.py`：Cookie 有效期、HMAC token、旧 Cookie 判定；三种模式共用的密码页工具。
- `website/redblue_ledger_api.py`：模式 A，红蓝台账 Cookie 登录/登出、旧 Cookie 401。
- `website/room_voice_replays_api.py`：模式 A，路径限定 Cookie、独立监控 Token、音频 Range 鉴权。
- `website/social_credentials_admin_api.py`：模式 A，短时会话 + 同源校验 + 凭据桥。
- `website/room_messenger_api.py` / `website/templates/room_messenger.html`：模式 A，房间信使；个人号 Token 不进网页进程，经本机 root 桥发送；即时发送要求确认词。
- `website/room_messages_api.py` / `website/templates/room_messages.html`：模式 B，请求头密码 + 页面内存。
- `website/flip_cards_api.py` / `website/templates/flip_cards.html`：模式 C，请求头密码 + 媒体短时签名 URL。
- `tests/test_password_page_security.py`：密码页静态护栏测试。
- `tests/test_password_verify_endpoints.py`：鉴权依赖与旧 Cookie 行为测试。
