# 真人感产品宣传片 · Codex Skill

`$make-product-trailer` 把一个产品的具体用法拍成短片。它用人物场景交代用户为什么打开产品，再用真实界面展示关键操作和可见成果。

## 安装

在有此私有仓库访问权限的 GitHub 账号下，使用 GitHub CLI 将技能克隆到 Codex 技能目录。首次使用 GitHub CLI 时先运行 `gh auth login`。

```bash
skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_root"
gh repo clone DeanHilarious/make-product-trailer "$skill_root/make-product-trailer"
```

## 调用

在目标产品的工作区打开 Codex，提供产品资料、可运行版本或已有录屏，再指定想展示的操作和发布渠道。

> 用 `$make-product-trailer` 给这个产品做一支 30 秒的真人感宣传片。用当前产品界面展示核心操作和实际成果，交付官网横版和抖音竖版，竖版烧录中文字幕。

人物镜头可以使用已有授权实拍，也可以按任务选择生成工具。选用火山方舟时，用已授权的 `arkcli` 配置生成素材。官网横版可附可切换的字幕，竖版可重新取景、放大关键操作并烧录字幕。

## 已有素材时直接合成

复制[时间线模板](assets/timeline.example.json)，填写镜头、时长、音轨和字幕。素材路径相对于时间线 JSON。从仓库根目录调用脚本，需要 Python 3 和 FFmpeg。

```bash
python3 scripts/compose.py /path/to/timeline.json trailer.mp4
```

若 FFmpeg 未在 `PATH` 中，追加 `--ffmpeg /path/to/ffmpeg`。烧录字幕使用 `caption_mode: "burn"`，需要支持 `subtitles` 滤镜的 FFmpeg 和字幕所需的字体。

## 仓库内容

- [SKILL.md](SKILL.md) 记录适用场景和完整工作流。
- [制作参考](references/production.md) 包含人物生成、产品录屏、剪辑及验收说明。
- [时间线模板](assets/timeline.example.json) 与[合成脚本](scripts/compose.py) 用于导出并验证 MP4。
