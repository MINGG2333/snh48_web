# 用户输入问题长度 / 字符限制配置

## 概述

为防止用户输入过长或包含特殊符号的问题，系统在前端和后端均设置了问题验证。默认限制为 **20 字**，并限制仅允许中文、英文字母、数字和常用标点符号。

---

## 验证规则

系统对用户输入的问题进行以下验证：

| 规则 | 说明 |
|------|------|
| **字数限制** | 有效字符（中文 + 英文字母 + 数字）不超过 `MAX_QUESTION_LENGTH`（默认 20） |
| **特殊符号限制** | 仅允许中文字符、英文字母、数字、空格和常用标点符号 |
| **非空校验** | 不能为空或只有空格 |

**允许的常用标点符号**：
```
，。！？、；：""''（）【】《》—…·,.?!;:()[]{}-～~
```

**会被拦截的特殊符号**示例：`@#$%^&*+=`、emoji（😊🔥✨）、数学符号（±÷≠）、其他 Unicode 符号等。

---

## 修改字数限制

需要修改以下 3 处关键值：

### 1. 前端 HTML — 浏览器输入限制

**文件**: `website/templates/qa.html`

```html
<input type="text"
       id="qaInput"
       class="qa-input"
       placeholder="为什么房间名叫葬爱家族？"
       maxlength="20"           ← 修改此处数字（浏览器端限制）
       disabled>
<span id="qaCharCount" class="qa-char-count">0/20</span>  ← 同时更新此处显示
```

> `maxlength` 属性控制浏览器端最多能输入多少个**字符**（不是有效字数），用户无法突破此限制。

### 2. 前端 JS — 配置常量

**文件**: `website/static/js/qa.js`

```javascript
// ── Config ──────────────────────────────────────────────────────────────
const MAX_QUESTION_LENGTH = 20;    // ← 修改此处数字（有效字符上限）
```

> 计数逻辑：`countMeaningful()` 函数只统计中文字符、英文字母、数字为有效字符，标点符号不计入。
> 特殊符号拦截：`hasBadChars()` 函数检测是否包含不允许的符号。

### 3. 后端 API — 服务端安全校验

**文件**: `website/qa_api/router.py`

```python
# ── Question validation ────────────────────────────────────────────────────
MAX_QUESTION_LENGTH = 20   # ← 修改此处数字
```

> 服务端使用 `validate_question()` 函数统一校验，在 `ask-async` 和 `ask` 两个端点入口均进行校验。
> 校验内容：非空、长度限制、特殊符号限制。

---

## 三层防护机制

| 层级 | 位置 | 作用 |
|------|------|------|
| 1. HTML | `qa.html` 的 `maxlength` | 浏览器直接阻止超长输入 |
| 2. JS | `qa.js` 的 `hasBadChars()` / `countMeaningful()` | 实时字符计数（黄/红提示）；提交时校验字数 + 特殊符号 |
| 3. 后端 | `router.py` 的 `validate_question()` | API 入口安全校验，防止绕过前端直接调用 |

---

## 修改允许的特殊符号

如需调整允许的标点符号列表，需要同步修改**前后端两处**：

### 前端 JS — `QUESTION_ALLOWED_RE`

**文件**: `website/static/js/qa.js`

```javascript
const QUESTION_ALLOWED_RE = /^[\u4e00-\u9fff a-zA-Z0-9，。！？、；：""''（）【】《》—…·,.?!;:()\[\]{}\-～~\s]+$/;
```

### 后端 Python — `_QUESTION_ALLOWED_RE`

**文件**: `website/qa_api/router.py`

```python
_QUESTION_ALLOWED_RE = re.compile(
    r'^[\u4e00-\u9fff a-zA-Z0-9'
    r'，。！？、；：""''（）【】《》—…·'
    r',\.\?!;:()\[\]{}\-～~\s]+$'
)
```

---

## 搜索变更位置

```bash
# 搜索前端 JS 中的配置
grep -n "MAX_QUESTION_LENGTH\|QUESTION_ALLOWED_RE\|countMeaningful\|hasBadChars" website/static/js/qa.js

# 搜索后端 Python 中的配置
grep -n "MAX_QUESTION_LENGTH\|validate_question\|_QUESTION_ALLOWED_RE" website/qa_api/router.py

# 搜索 HTML 模板中的 maxlength
grep -n "maxlength\|qaCharCount" website/templates/qa.html
```
