# 天山哨兵 Tianshan Sentinel

面向城市建设、园区扩张与生态巡查的多时相遥感变化监测及可解释风险研判平台。系统以监测项目为业务单元，接收同一区域两个或多个时相的航拍、卫星影像，完成配准、像素级变化分割、置信度估计、变化斑块统计、风险分级、人工复核和成果归档。

## 核心能力

- 多尺度注意力孪生网络：共享 ResNet18 编码器，提取两期图像特征并通过差异门控融合。
- 输入质量门控：结合宽高比、ORB 特征、RANSAC 内点覆盖和单应变换几何约束，拒绝非同一区域或无法可靠配准的影像对。
- 可信推理：支持温度缩放、双向时相融合、多尺度滑窗、模型种子引导的结构变化融合、不确定性、置信度和变化面积统计。
- 轻薄本可演示：未放置权重时自动启用 OpenCV 启发式基线；训练后优先使用 ONNX Runtime CPU 推理。
- 多时相项目闭环：监测项目、相邻时相批量分析、变化趋势、阈值预警、斑块复核和审计历史。
- 标准化成果输出：生成带影像证据和斑块清单的 DOCX/PDF 报告，导出 GeoJSON 变化斑块与项目时间轴 CSV。
- 工程化交付：FastAPI、Vue 3、ECharts、SQLite、Docker、API 文档和自动测试。
- 可审计实验：已保存逐轮训练曲线、校准指标、测试指标、ONNX 一致性、本机时延和定性案例，不填写未运行的消融结果。

## 已完成训练

模型已在 LEVIR-CD 裁剪版上完成初始训练和一次增量微调。初始训练在 RTX 3080 Ti 上运行 76 轮并早停；增量阶段从第 64 轮最佳权重继续训练 21 轮，加入时相交换、独立光照/色彩、局部阴影和轻微模糊增强。最终部署候选在 2048 对独立测试样本上取得 IoU 0.820103、F1 0.901161，分别高于旧正式模型的 0.815886 和 0.898609。

固定压力验证中，旧模型在色彩、阴影和混合扰动下的平均 IoU 为 0.639943，最终微调模型为 0.814982；干净验证 IoU 仅变化 -0.000113。ONNX 与 PyTorch 最大绝对误差为 0.00001144，本机 CPU 单次前向平均 70.43 ms。

最终部署文件为 `artifacts/model.onnx` 与 `artifacts/model.metadata.json`，通过 [v1.0.0 Release](https://github.com/yaonikaixin999999/TianshanSentinel/releases/tag/v1.0.0) 单独下载，不存放在 Git 历史中。指标和适用边界见 `docs/10_真实训练结果.md`，其中完整训练日志等本地产物未全部随源码发布。

## 目录

```text
TianshanSentinel/
  src/tianshan_sentinel/  # 数据、模型、损失、训练与推理核心
  backend/app/            # FastAPI 服务与 SQLite 仓储
  frontend/               # Vue 3 + ECharts 看板
  configs/                # 训练配置
  scripts/                # 训练、评估、校准、导出和演示脚本
  tests/                  # 单元与接口测试
  docs/                   # 项目全套文档
  deploy/                 # Docker 部署文件
```

## 有效输入与演示样本

正式模型只检测建筑新增、扩建和拆除。有效的输入对必须覆盖同一地理区域，方向、比例尺和空间范围基本一致；应使用真实不同时期的遥感影像，不能用调色、阴影、滤镜或生成式编辑代替时相变化。车辆、植被、道路、地表颜色和成像风格变化不属于当前模型的正类。

模型以 LEVIR-CD 的 256 x 256 配准切片训练。部署推理会对大幅影像自动执行 256 与 384 像素多尺度重叠滑窗，不再把整幅长方形影像拉伸成单张正方形输入；每个窗口同时执行前后、后前双向推理，以同等方式检测建筑新增和拆除。最可靠的验收数据仍是 LEVIR-CD `A/test` 与 `B/test` 目录中的同名图像。

对存在明显合成重绘、跨传感器色调差异或大面积拆除的域外大幅影像，部署层还会计算局部标准化、结构相似性、边缘密度和自适应直方图证据。结构证据不能独立报出变化，只有与一个或多个正式模型斑块连通时才会扩展掩膜；纯亮度变化回归测试不会触发扩展。标准 256 x 256 输入直接采用模型结果，不启用结构扩展；大图触发扩展时，引擎名带有 `+structural-fusion`，新增区域同时提高不确定性。网页“变化占比”统计最终融合掩膜占全图的比例，并不等同于拆除地块的测绘面积。

网页“载入示例”现使用测试集高分案例 `001097`，由 `artifacts/examples/case_high.png` 提取。增量微调 ONNX 双向推理的端到端结果为变化占比 5.41%、5 个有效斑块；自动测试会验证该示例必须保持在 3%-15%，不得错误触发结构扩展，且交换前后时相不会改变结果。

## 本地启动

推荐环境：Python 3.11、Node.js 22、pnpm 10。下面的命令使用 PowerShell；从项目根目录运行后端。

```powershell
git clone https://github.com/yaonikaixin999999/TianshanSentinel.git
cd TianshanSentinel
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[inference,test]'
npm install --global pnpm@10
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run build
```

### 下载已训练模型

在 [v1.0.0 Release](https://github.com/yaonikaixin999999/TianshanSentinel/releases/tag/v1.0.0) 下载 `tianshan-sentinel-onnx-v1.0.0.zip`，解压到项目根目录。ZIP 自带 `artifacts` 目录，解压后的路径必须是：

```text
TianshanSentinel/
  artifacts/
    model.onnx
    model.metadata.json
```

可在项目根目录执行：

```powershell
Expand-Archive -LiteralPath "你的下载目录\tianshan-sentinel-onnx-v1.0.0.zip" -DestinationPath . -Force
```

原始 ONNX 的 SHA-256 为 `ae9b1b2ea3b208227c84290a891ffd1806d399ddc48a8486270a4c5b84707101`，可用 `Get-FileHash artifacts/model.onnx -Algorithm SHA256` 核对。权重仅作为学术研究、教学复现材料提供，来源条件见 [第三方说明](THIRD_PARTY_NOTICES.md)。

### 运行服务

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。FastAPI 同时托管构建好的前端，无需另开前端服务。API 文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)，健康检查位于 `/api/v1/health`；模型正常加载时引擎为 `onnxruntime-siamese-resnet18`。在终端按 `Ctrl+C` 停止。

未下载权重时，项目仍可运行，但使用 OpenCV 启发式基线，不具备正式建筑变化模型的准确率。正式模型仅适用于同一区域、已配准或可可靠配准的建筑遥感影像对；不同场景的普通照片不能用作有效验收数据。

修改前端代码时可以另开终端执行 `pnpm --dir frontend run dev`，浏览器打开 `http://localhost:5173`，后端继续运行在 8000 端口。

只有在重新导出 `artifacts/examples/case_high.png` 后，才需要运行 `python scripts/make_demo_assets.py` 重新生成网页示例。

## 构建与测试

```powershell
python -m pytest
pnpm --dir frontend run build
```

上述安装包含应用、ONNX 推理和接口测试依赖。未安装训练依赖时，涉及 PyTorch 的测试会跳过；未下载 ONNX 权重时，正式模型示例回归测试也会跳过。完整模型验证需要安装 `.[train,test]` 并准备模型和数据，详见 `docs/07_测试与验收方案.md`。

## 云 GPU 训练

1. 执行 `python -m pip install -e '.[train,test]'` 安装训练依赖，并阅读 [数据使用条件](THIRD_PARTY_NOTICES.md)。然后执行 `python scripts/prepare_levir_cd.py`，下载并整理固定版本的 LEVIR-CD 裁剪数据；也可手动整理为 `data/LEVIR-CD/{train,val,test}/{A,B,label}`。
2. 执行环境与数据检查：`python scripts/validate_dataset.py --root data/LEVIR-CD`。
3. 初始训练：`python scripts/train.py --config configs/levir_cd.yaml`。
4. 增量微调：`python scripts/train.py --config configs/levir_cd_finetune.yaml`。
5. 鲁棒性比较：运行 `scripts/evaluate_robustness.py`，在固定干净/色彩/阴影/混合压力集上筛选候选。
6. 校准、验证集阈值选择与测试：依次执行 `scripts/calibrate.py`、`scripts/select_threshold.py` 和 `scripts/evaluate.py`。
7. 导出：`python scripts/export_onnx.py --checkpoint artifacts/levir_cd_finetune/selected_final.pt --output artifacts/model.onnx`。

完整说明见 `docs/06_云GPU训练与部署指南.md`。

## 关键接口

- `GET /api/v1/health`：服务和推理引擎状态。
- `POST /api/v1/analyses`：上传 before/after 图像，并可关联项目及两个时相标签；影像不具可比性时返回 `422`。
- `GET /api/v1/analyses`：历史记录，可按 `project_id` 筛选。
- `GET /api/v1/analyses/{id}`：单次分析详情。
- `PATCH /api/v1/analyses/{id}/regions/{region_id}`：提交事件类型、确认/排除状态和复核备注。
- `GET/POST/PATCH /api/v1/projects`：监测项目查询、创建和设置。
- `GET /api/v1/projects/{id}/timeline`：项目多时相变化趋势。
- `GET /api/v1/reviews`：斑块复核队列。
- `GET /api/v1/analyses/{id}/exports/report.docx`：Word 审计报告。
- `GET /api/v1/analyses/{id}/exports/report.pdf`：PDF 定版报告。
- `GET /api/v1/analyses/{id}/exports/regions.geojson`：变化斑块 GeoJSON。
- `GET /api/v1/projects/{id}/exports/timeline.csv`：项目时间轴 CSV。
- `GET /api/v1/statistics`：看板统计。

平台操作说明见 `docs/11_平台功能使用指南.md`，完整字段定义见 `docs/05_API接口文档.md`。

## 许可证与来源

原创代码和原创文档采用 [MIT License](LICENSE)。LEVIR-CD 演示图片、数据和已训练模型不在 MIT 授权范围内，按来源条件用于学术研究；使用前请阅读 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。论文、学生记录、评分表、用户上传图片、运行数据库、云主机账号和密码均不随开源仓库发布。
