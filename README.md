<p align="center"><img src="web/logo.svg" width="96" alt="Star7 Director"></p>
<h1 align="center">Star7 导演台 · Star7 Director</h1>
<p align="center">在 ComfyUI 画布里管理素材、分镜、生成队列和镜头版本。</p>

首个公开预览版，面向 MiniMax H3。模型加载、LoRA 和前置节点保留在 ComfyUI 画布上；导演台负责镜头设置、素材引用、顺序生成及一采、高清二采、人脸修复的阶段调度。

## 功能

- 人物、场景、物品、音色、视频与特效素材卡，使用 `@` 在提示词中引用。
- 分镜 JSON 文件导入、拖入、检查、导出，保留镜头参数和种子设置。
- 在选中镜头后或列表末尾添加镜头，拖动调整顺序。
- 当前镜头重新生成、批量选择生成、继续生成全部，以及可查看和取消的后台队列。
- 独立镜头、尾帧参考、运动引导和智能首尾帧；可预先选择使用上段视频尾帧作为首帧。
- 一采实时预览、可播放阶段成品、高清二采、人脸修复及当前画面阶段说明。
- 参数改动明细；普通前段参考变化单独提示，避免批量生成时连锁重跑。
- 浏览器刷新后恢复后台任务状态；服务退出后保留已经写盘的结果。
- 一项目一文件夹、本地项目管理、项目包、素材库包、连续预览和成片导出。

## 安装

1. 在 ComfyUI 的 `custom_nodes` 目录中执行：

   ```bash
   git clone https://github.com/star7code/star7-director.git
   ```

2. 安装 [MiniMax H3 Chunk — Star7](https://github.com/star7code/minimax-h3-chunk-star7)。示例工作流还使用 [VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)。请按这两个项目的说明安装其依赖。
3. 在 ComfyUI 使用的 Python 环境中安装本项目依赖：

   ```bash
   python -m pip install -r custom_nodes/star7-director/requirements.txt
   ```

   便携版请使用其 `python_embeded/python.exe`，不要另建不相关的环境。PyTorch 使用已有 ComfyUI 环境的版本。
4. 确认 FFmpeg 可用。随后通过你正常使用的启动器重启 ComfyUI。
5. 导入 `workflows/Star7-Director-H3-画布导演台.json`，在前置节点选择本机已有的 H3 模型、LoRA、CLIP 和视频/音频 VAE。

模板不附带模型权重或个人素材。标准示例使用小画布和短镜头，建议先完成一段生成，再增加时长和分辨率。旧的 `完整测试工作流` 是展开链参考，日常使用画布导演台模板。

## 使用

在左侧素材库添加素材，在右侧镜头描述里用 `@` 选择引用。人物可以绑定音色。素材 ID 稳定，改名不会自动替换提示词里的普通文字。

镜头设置与全局生成参数保存在工作流中。分享普通工作流不会携带本地素材文件；接收者会看到缺失引用提示，可以编辑原素材卡补齐文件。项目包包含素材与镜头配置，适合完整迁移；模型权重仍需接收者自行准备。

“继续生成全部”处理未完成或确实需要更新的镜头；“仅重新生成当前”明确重跑该镜头。已有二采或修脸成品不会仅因为关闭选项而被自动降级。生成中可以继续添加生成请求，顺序可在“查看队列”中检查。

种子栏显示当前配置值；首次生成使用该值。递增/递减模式在已有成功生成记录后决定下一次重生成的种子。导入分镜配置后，以导入的种子和生成控制重新开始。

普通连续性引用的前段一采画面变化只提示当前镜头尚未更新，不自动加入全部生成；前段仅二采/修脸不触发该提示。智能首尾帧使用上段尾帧时，前段基础画面变化属于实际输入变化。

## 数据与缓存

运行数据在插件自己的 `data/` 中，每个项目使用 `data/projects/<项目ID>/` 保存配置、素材、任务记录和辅助缓存。正式视频在 ComfyUI 的 `output/Star7-Director/年月日/` 中。

**Git 仓库和源码发布包不包含 `data/`、本地素材、模型、latent 缓存、运行日志或生成视频。** 更新代码时请保留现有 `data/`；不要把删除项目数据当作更新步骤。缓存管理入口用于按范围清理辅助缓存。

- [文件管理](docs/STORAGE.md)
- [分镜交换格式](docs/storyboard-format.md)
- [连续性说明](docs/continuity.md)
- [架构与状态规则](docs/DESIGN.md)

## 验证与边界

公开版本包含后端单元回归，覆盖分镜、素材包、项目存储、种子、缓存复用、参数判定、队列及预览恢复；这些检查不执行 GPU 采样。真实输出质量、显存需求及连续性效果取决于模型、驱动、ComfyUI 与依赖节点组合。

后台任务在服务运行时继续执行，关闭浏览器和退出 ComfyUI 服务是不同情况。源码发布不会修改启动器、升级 ComfyUI 核心或替换已有模型环境。

## 许可与致谢

Star7 源码采用 MIT 许可。`vendor/aimixer` 中衍生的连续性适配代码保留 Apache-2.0 许可、原版权和 [来源说明](vendor/aimixer/NOTICE.md)。模型及外部节点遵循各自许可。

感谢 MiniMax、ComfyUI、AIMixer 与 VideoHelperSuite 的基础实现。
