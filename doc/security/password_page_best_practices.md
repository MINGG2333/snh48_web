# 密码保护页面与后台鉴权最佳实践

> 更新日期：2026-10-25
>
> 适用范围：本仓库所有带访问密码的页面、管理后台、写入 API 和异步任务入口。
>
> 强制要求：新增或修改密码页、登录接口、Cookie/Token 会话前，先读本文；实现完成后按本文测试清单验收。

## 1. 结论先行

1. **密码只用于一次登录验证，浏览器持久层不保存明文密码。**
2. **默认方案是服务端签发 HttpOnly Cookie**：前端 `POST /login` 提交密码，服务端校验后种下 `HttpOnly`、`Secure`、`SameSite=Strict`、路径限定的签名 Cookie；后续请求由浏览器自动携带。
3. **禁止**把密码写入 `localStorage`、`sessionStorage`、IndexedDB、JS 可读 Cookie 或 URL。
4. **禁止**在密码输入框使用 `autocomplete="current-password"`。本仓库统一使用 `autocomplete="new-password"`，避免浏览器密码管理器自动保存后台密码。
5. **页面壳可以为公开 HTML，但每个数据/写入 API 必须独立鉴权。** 不能只靠前端隐藏页面。
6. **`/verify` 只做轻量鉴权检查，不返回业务数据，并设置 `Cache-Control: no-store`。**

## 2. 推荐登录流程

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

Cookie 的 `Path` 必须限定到该功能的 API 前缀，例如 `/api/redblue`，不要使用 `/`。
Cookie 的值必须是服务端生成的签名 token，不能是密码本身，也不能是可逆编码。

## 3. 服务端实现清单

### 3.1 常量与 token

```python
AUTH_COOKIE = "xxx_auth"
AUTH_COOKIE_MAX_AGE = 24 * 60 * 60
_COOKIE_SECRET = os.urandom(32)


def _cookie_token(password: str) -> str:
    return hmac.new(_COOKIE_SECRET, password.encode("utf-8"), hashlib.sha256).hexdigest()
```

- 用 `hmac.compare_digest` 比较密码和 Cookie token。
- 不要把密码、token 或 `_COOKIE_SECRET` 写进日志、异常详情、分析事件或响应体。
- 当前仓库的单进程实现使用 `os.urandom(32)`，服务重启后旧 Cookie 失效，页面会回到登录页，这是可接受的。
- 如果未来改成多 worker，必须把 `_COOKIE_SECRET` 改为所有 worker 共享的持久密钥（环境变量或 600 权限密钥文件），否则不同 worker 签发的 Cookie 会互相失效。

### 3.2 鉴权依赖

```python
def verify_xxx_password(
    request: Request,
    x_xxx_password: str = Header(None, alias="X-Xxx-Password"),
    xxx_auth: str = Cookie(None, alias=AUTH_COOKIE),
):
    expected = cfg.XXX_PASSWORD
    if not expected:
        raise HTTPException(status_code=403, detail="功能未启用")
    if xxx_auth and hmac.compare_digest(xxx_auth, _cookie_token(expected)):
        return True
    if x_xxx_password and hmac.compare_digest(x_xxx_password, expected):
        return True
    if not xxx_auth and not x_xxx_password:
        check_login_limit(request)  # 只对失败尝试计数
        raise HTTPException(status_code=401, detail="需要密码")
    check_login_limit(request)
    raise HTTPException(status_code=403, detail="密码错误")
```

- Cookie 优先，请求头密码只作为旧客户端/测试兼容入口；新前端不得再发送密码请求头。
- 未配置密码时返回 403，不能降级为公开访问。
- 失败尝试必须限速；成功登录不应消耗失败额度。

### 3.3 登录与登出

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
        value=_cookie_token(expected),
        max_age=AUTH_COOKIE_MAX_AGE,
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
- 登录、登出、`/verify` 和业务响应都应设置 `Cache-Control: no-store`，避免代理或浏览器缓存敏感内容。

### 3.4 密码配置

- 密码只放在服务器 `.env` 或 600 权限密钥文件，不进入 Git、文档、日志、对话或前端构建产物。
- 新密码项必须同步更新 `.env.example` 的键名和说明，但值留空或写占位符。
- 不同敏感级别的页面应使用独立密码。默认复用链（如 `REDBLUE_LEDGER_PASSWORD -> BUSINESS_ADMIN_PASSWORD -> GIFT_REPLIES_PASSWORD`）会放大单点泄露影响，新增高敏感页面时优先显式设置独立密码。

## 4. 前端实现清单

### 4.1 登录表单

```html
<input id="passwordInput" type="password" autocomplete="new-password" placeholder="密码">
```

禁止：

```html
<!-- 不要这样写 -->
<input type="password" autocomplete="current-password">
```

### 4.2 登录

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

- 登录成功后立即清空输入框。
- 不把密码赋给全局变量、不发 `X-Xxx-Password` 请求头、不写任何 Web Storage。
- 旧版本如果用过 Web Storage，升级时在启动阶段执行一次 `removeItem` 清理历史 key，但不要恢复写入。

### 4.3 启动时检查会话

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

### 4.4 业务请求与失效处理

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
- 导出、下载、轮询、自动同步也必须走同一套 Cookie 鉴权，不能只在主数据接口加 Cookie。

### 4.5 登出

```javascript
await fetch("/api/xxx/logout", {
  method: "POST",
  credentials: "same-origin",
  cache: "no-store",
});
location.reload();
```

## 5. 测试清单

新增密码页至少补齐以下测试：

1. **登录成功**：`POST /login` 返回 200，`Set-Cookie` 包含 `HttpOnly`、`Secure`、`SameSite=strict`、正确 `Path`。
2. **Cookie 鉴权**：带 Cookie 访问 `/verify`、数据接口、导出接口均成功。
3. **登出**：`POST /logout` 后数据接口返回 401。
4. **错误密码**：返回 403，不种 Cookie。
5. **兼容入口**：旧请求头密码如保留，单独测试；新前端不得依赖它。
6. **静态护栏**：密码模板不得出现 `autocomplete="current-password"`，不得出现密码写入 `localStorage`/`sessionStorage`。参考 `tests/test_password_page_security.py`。
7. **前端语法**：内联 JS 通过 `node --check`；静态 JS 改动后运行 `node script/obfuscate_js.cjs`。
8. **线上烟测**：未登录 401、登录 200、带 Cookie 数据/导出 200、登出后 401，且 Set-Cookie 属性正确。

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
| `sessionStorage.setItem("xxx_password", password)` | 明文密码可被同源 JS、扩展、共享设备读取；刷新/会话恢复后继续有效 | HttpOnly Cookie token |
| `localStorage.setItem("xxx_password", password)` | 长期明文落盘，风险高于 sessionStorage | 立即迁移并清理旧 key |
| `autocomplete="current-password"` | 浏览器密码管理器可能自动保存后台密码 | `autocomplete="new-password"` |
| 页面加载时直接读取已保存密码并自动登录 | 共享浏览器标签页可无感进入后台 | 服务端 Cookie 会话 + `/verify` |
| 只保护页面 HTML，不保护 API | 直接请求 API 可绕过页面 | 每个数据/写入接口加鉴权依赖 |
| 把密码放 URL/query | 进入浏览器历史、代理日志、Referer | POST body + HTTPS |
| 登录失败不限速 | 可被暴力尝试 | 失败限速 + 通用错误信息 |
| Cookie `Path=/` | 同域其他页面也会携带管理 Cookie | `Path=/api/xxx` |
| 登出只清前端变量 | HttpOnly Cookie 仍有效 | 调用服务端 `/logout` 删除 Cookie |
| 多个页面共用同一密码 | 一处泄露影响全部后台 | 高敏感页面使用独立密码 |

## 7. 旧页面迁移步骤

1. 后端增加 `AUTH_COOKIE`、`/login`、`/logout`，鉴权依赖改为 Cookie 优先、请求头兼容。
2. 前端登录改为 `POST /login`，删除密码全局变量、密码请求头和 Web Storage 写入。
3. 启动流程改为调用 `/verify`；401/403 回登录，其他错误允许重试。
4. 导出、轮询、自动同步等所有请求统一带 `credentials: "same-origin"`。
5. 清理历史存储 key（只 `removeItem`，不写回）。
6. 补测试和静态护栏，部署后做未登录/登录/登出三段烟测。
7. 更新 `doc/website_pages.md`、`doc/security/security_baseline.md` 和运行快照。

## 8. 上线前审查清单

- [ ] 浏览器持久层没有密码；旧 key 已清理。
- [ ] 密码框使用 `autocomplete="new-password"`。
- [ ] 登录接口只接收 POST JSON，密码不进 URL。
- [ ] Cookie 为 `HttpOnly; Secure; SameSite=Strict; Path=/api/xxx`。
- [ ] Cookie 值是服务端 HMAC token，不是密码。
- [ ] `/verify`、业务数据、导出、轮询全部鉴权。
- [ ] 登录失败有限速，错误信息不区分“用户不存在/密码错误”。
- [ ] 登出调用服务端接口并删除 Cookie。
- [ ] 401/403 统一回登录；其他错误允许重试。
- [ ] 单元测试、静态护栏测试、前端语法检查通过。
- [ ] `doc/website_pages.md` 和 `doc/security/security_baseline.md` 已更新。
- [ ] 线上未登录 401、登录 200、带 Cookie 访问 200、登出后 401。

## 9. 参考实现

- `website/redblue_ledger_api.py`：红蓝台账 Cookie 登录/登出、Cookie 优先鉴权、请求头兼容。
- `website/flip_cards_api.py`：路径限定 Cookie、登录/登出、账号管理同源校验。
- `website/room_voice_replays_api.py`：路径限定 Cookie、独立监控 Token、音频 Range 鉴权。
- `website/templates/redblue_ledger_2026.html`：登录、`/verify` 启动检查、401/403 回登录、导出走 Cookie。
- `tests/test_password_page_security.py`：密码页静态护栏测试。
