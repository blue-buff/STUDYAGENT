# 资源约束补充说明

> 本机 MacBook Pro 2016 / 双核 i7 / **8GB 内存** / SSD **仅剩 13GB**
> 以下补充说明追加到对应路径的原提示词中。

---

## Path 1（Playwright）— 补充

```
资源约束补充：
- 你是唯一有权启动 Chrome 的路径。其他需要浏览器的路径会等你的结果。
- 登录成功后保存 storage-state.json 到 /Users/song/project/STUDYAGENT/get from web/shared/，供 Path 3/6 读取。
- 截图总量控制在 200MB 以内。
- 完成工作后执行 zujuan shutup 关闭 Chrome，然后创建一个标记文件 /Users/song/project/STUDYAGENT/get from web/shared/chrome_freed 表示 Chrome 已释放。
```

---

## Path 3（菁优网）— 补充

```
资源约束补充：
- 不要自己启动 Chrome。8GB 内存跑两个 Chrome 会卡死。
- 分两步走：
  第一步（现在就可以做）：用 requests 静态分析 jyeoo.com 页面结构、URL 规则、学科分类。不需要登录就能爬的内容先爬下来。
  第二步（等 Path 1 释放 Chrome 后）：检查 /Users/song/project/STUDYAGENT/get from web/shared/chrome_freed 是否存在。存在时可以用 Playwright 做登录和动态抓取。
- 截图控制在 100MB 以内。
```

---

## Path 4（数据集）— 补充

```
资源约束补充：
- 磁盘仅剩 13GB。下载数据集总量控制在 2GB 以内。
- 优先选 HuggingFace 的 streaming 模式（不落盘），或只下载数据集的子集/采样。
- 解压后的中间文件即刻删除，只保留最终清洗好的 JSON（预计 <100MB）。
- 下载任何超过 500MB 的文件前，先打印大小并停下来确认。
```

---

## Path 6（学科网试卷）— 补充

```
资源约束补充：
- 不要自己启动 Chrome。Path 1 也在操作 zujuan.xkw.com（同体系），等它完成后再考虑浏览器方案。
- 优先用 requests 做静态分析：抓页面 HTML 看试卷结构、URL 规则、免费范围。
- 如果必须用 Playwright，等待 /Users/song/project/STUDYAGENT/get from web/shared/chrome_freed 文件出现后再操作，并复用 Path 1 可能留下的 storage-state.json。
- 测试用的试卷不超过 10 份，中间文件处理完即删。
```

---

## Path 8（文档搜索）— 补充

```
资源约束补充：
- 磁盘仅剩 13GB。下载试卷文档控制在 5 份以内（仅做流程验证），不要批量下载。
- 优先从百度文库/道客巴巴的页面 HTML 直接提取文本，跳过文件下载。
- 不要安装本地 OCR 模型（会占用几 GB），如需 OCR 用 API 调用。
- 验证完流程后清理所有下载的 PDF/DOC 文件。
```

---

## Path 2 / 5 / 7

无需补充，原提示词直接用。这三个路径不涉及浏览器、不下载大文件、不占磁盘。
