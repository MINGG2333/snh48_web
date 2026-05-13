# Favicon 管理说明

## 概述

网站标签页图标（favicon）支持**多个 logo 轮播显示**，每次刷新页面随机展示一个。

## 图片管理流程

### 📥 1. 准备图片

将你的正方形 logo 图片放到项目根目录的 `img/` 文件夹下，支持以下格式：

| 格式 | 说明 |
|------|------|
| `.jpg` / `.jpeg` | 常见格式 |
| `.png` | 常见格式 |
| `.heic` / `.heif` | 苹果设备导出格式（自动转换） |

> ⚠️ 建议全部使用**正方形**图片，非正方形图片会自动居中裁剪为正方形。

### 🛠️ 2. 生成 favicon

```bash
# 进入项目目录
cd /home/snh48_web

# 运行转换脚本（自动扫描 img/ 下的所有图片，转换为 64x64 PNG）
conda run -n koudai48 python script/convert_favicons.py
```

运行效果示例：
```
源目录: /home/snh48_web/img
输出目录: /home/snh48_web/website/static/images/favicons
目标尺寸: 64x64px
找到 5 张图片:

  ✓ IMG_xxx.JPG (1018x1018) → favicon1.png
  ✓ IMG_xxx.PNG (920x920) → favicon2.png
  ✓ IMG_xxx.HEIC (1201x1201) → favicon3.png
  ✓ ...

处理完成: 5/5 张成功
```

### 🔄 3. 重启服务

```bash
# 杀掉旧进程
pkill -f "website.main"

# 启动新服务
screen -S snh48 -dm bash -c "cd /home/snh48_web && source venv/bin/activate && python -m website.main 2>&1 | tee /var/log/snh48/snh48_screen.log"
```

### ✅ 4. 验证

```bash
# 多请求几次，看是否每次随机返回不同图标（md5不同说明轮播成功）
for i in 1 2 3 4 5; do
  curl -s -o /tmp/favicon_test_$i.png http://localhost:8000/favicon.ico
  md5sum /tmp/favicon_test_$i.png
done
```

## 注意事项

- **增加/替换 logo**：只需更新 `img/` 目录下的文件，重新运行脚本、重启服务即可
- **删除 logo**：从 `img/` 中删除文件，重新运行脚本即可
- **脚本会自动清空旧 favicon 目录**，无需手动删除
- 脚本会自动注册 HEIC 解码器，苹果手机导出的 `.HEIC` 文件也能直接处理

## 相关文件

| 文件 | 作用 |
|------|------|
| `img/*` | 源图片（你的 logo 原图） |
| `script/convert_favicons.py` | 转换脚本 |
| `website/static/images/favicons/` | 生成的 favicon PNG（自动生成，无需手动管理） |
| `website/main.py` | FastAPI 路由，负责轮播逻辑 |
| `website/templates/base.html` | 模板中引用 `/favicon.ico` |
