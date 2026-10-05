# 云 GPU 训练与部署指南

## 1. 推荐环境

- Ubuntu 22.04
- Python 3.11
- NVIDIA 驱动与 CUDA 12.x 兼容的 PyTorch
- 16 GB 以上 GPU 显存更宽裕；8 GB 显存可把 batch size 降为 4
- 30 GB 以上磁盘用于数据、日志和权重

不锁定具体云厂商。创建实例后先运行 `nvidia-smi`，确认驱动和显存可见。

## 2. 上传并安装

```bash
git clone https://github.com/yaonikaixin999999/TianshanSentinel.git
cd TianshanSentinel
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[train,test]'
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

若云平台镜像已预装不同 CUDA 版本的 PyTorch，优先按 PyTorch 官方矩阵安装对应 wheel，再执行 `pip install -e .`。不要混装多个 CUDA wheel。

## 3. 数据准备

自动下载并准备本次实验使用的 LEVIR-CD 256 x 256 裁剪版：

开始下载前，请阅读 [第三方使用条件](../THIRD_PARTY_NOTICES.md)。LEVIR-CD 官方仅允许学术用途，并要求遵守 Google Earth 使用条款，项目 MIT 许可不包含数据或已训练权重。

```bash
python scripts/prepare_levir_cd.py
python scripts/validate_dataset.py --root data/LEVIR-CD
```

也可以自行把 LEVIR-CD 放到 `data/LEVIR-CD`，目录结构见 `04_数据集与标注规范.md`。自动脚本固定数据仓库版本、记录 Parquet 校验值，并把标签规范化为 0/255 PNG。

先做 20 对样本的冒烟训练，确认 loss 能下降，再提交 80 epoch 完整任务。

## 4. 训练

```bash
mkdir -p artifacts
python scripts/train.py --config configs/levir_cd.yaml 2>&1 | tee artifacts/train_console.log
```

显存不足时修改：

```yaml
data:
  batch_size: 4
  image_size: 256
```

仍不足可改 batch size 2。AMP 默认开启。不要先把图像尺寸降得过小，因为小建筑边界会丢失。

主要产物：

- `best.pt`：验证集 IoU 最佳权重。
- `last.pt`：最后一轮权重。
- `history.json`：逐轮训练与验证指标。
- `summary.json`：设备、耗时和最佳 IoU。

## 5. 评估和校准

已有 `artifacts/levir_cd_run/best.pt` 时，可用专用配置做增量微调：

```bash
python scripts/train.py --config configs/levir_cd_finetune.yaml
```

该配置从旧 checkpoint 初始化，降低学习率，并启用时相交换、两时相独立光照/色彩、局部阴影和轻微模糊增强。训练器先计算源模型 baseline，只有验证 IoU 更高时才覆盖微调目录中的 `best.pt`。用以下命令比较干净与受扰动验证集；实际部署候选应同时满足干净性能回退可控和鲁棒性提升：

```bash
python scripts/evaluate_robustness.py \
  --checkpoint source=artifacts/levir_cd_run/best.pt \
  --checkpoint best=artifacts/levir_cd_finetune/best.pt \
  --checkpoint last=artifacts/levir_cd_finetune/last.pt \
  --data-root data/LEVIR-CD \
  --output artifacts/levir_cd_finetune/robustness_comparison.json
```

本项目这次实验根据压力验证选择了增量训练的 `last.pt`。重新训练时，应先检查上述比较结果再选择候选，不能只因为文件名相同就认定其性能一致。以下命令以 `last.pt` 为候选，先校准概率，再在验证集选择阈值，输出同一份最终部署 checkpoint `selected_final.pt`：

```bash
python scripts/calibrate.py \
  --checkpoint artifacts/levir_cd_finetune/last.pt \
  --data-root data/LEVIR-CD \
  --output artifacts/levir_cd_finetune/selected_final.pt

python scripts/select_threshold.py \
  --checkpoint artifacts/levir_cd_finetune/selected_final.pt \
  --data-root data/LEVIR-CD \
  --output artifacts/levir_cd_finetune/selected_final.pt

python scripts/evaluate.py \
  --checkpoint artifacts/levir_cd_finetune/selected_final.pt \
  --data-root data/LEVIR-CD \
  --output artifacts/metrics.json
```

温度缩放主要改善概率可信度，未必改变固定阈值下的 IoU。`calibration_metrics.json` 记录校准前后的 NLL、Brier 和 15 桶 ECE。阈值只在验证集上选择，测试集仅用于一次最终报告，避免测试集调参。论文应分别解释分割性能和概率校准。

## 6. 导出 ONNX

```bash
python scripts/export_onnx.py \
  --checkpoint artifacts/levir_cd_finetune/selected_final.pt \
  --output artifacts/model.onnx

python scripts/verify_onnx.py \
  --checkpoint artifacts/levir_cd_finetune/selected_final.pt \
  --model artifacts/model.onnx
```

下载到轻薄本后，把 `model.onnx` 和同时生成的 `model.metadata.json` 一起放入 `artifacts/`。侧车文件保存验证集选出的概率阈值和输入尺寸；缺少时后端会回退为 0.5 和 256。重启后端，访问 `/api/v1/health`，应显示 `onnxruntime-siamese-resnet18`。

无需重新训练时，可以直接从 [v1.0.0 Release](https://github.com/yaonikaixin999999/TianshanSentinel/releases/tag/v1.0.0) 下载 `tianshan-sentinel-onnx-v1.0.0.zip`，解压到项目根目录。ZIP 内包含 `artifacts/model.onnx` 和 `artifacts/model.metadata.json`，请保留这两个文件的同级关系。权重按第三方来源条件用于学术研究和教学复现，不纳入源码 MIT 许可。

在实际演示电脑上记录 100 次单批次 ONNX 前向延迟：

```bash
python scripts/benchmark_onnx.py --model artifacts/model.onnx
```

结果写入 `artifacts/onnx_cpu_benchmark.json`。该值只表示 256 x 256、batch size 1 的模型前向，不包含图像配准、上传和可视化时间。

## 7. 本地运行

推荐 Python 3.11 和 Node.js 22。激活项目虚拟环境后，在项目根目录执行：

```powershell
python -m pip install -e '.[inference,test]'
npm install --global pnpm@10
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run build
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。服务会同时托管构建好的前端。已训练模型需要按上一节放入 `artifacts/`；未下载权重时会启用 OpenCV 启发式基线，该基线不等同于正式建筑变化检测模型。

开发前端时，另开终端在项目根目录运行：

```powershell
pnpm --dir frontend run dev
```

开发页面地址为 `http://localhost:5173`，后端仍运行在 8000 端口。

## 8. Docker

```bash
docker compose up --build
```

浏览器打开 `http://localhost:8080`。模型目录以只读方式挂载，运行数据保存在 `runtime/`。

## 9. 训练记录模板

| 字段 | 记录值 |
|---|---|
| 云平台/实例 | 待填 |
| GPU | 从 summary.json 填 |
| PyTorch/CUDA | 从 summary.json 填 |
| commit 或压缩包版本 | 待填 |
| 随机种子 | 2026 |
| batch/image size | 从 summary.json 填 |
| 总训练时长 | 从 summary.json 填 |
| 最佳 epoch | 从 best.pt 填 |
| Test IoU/F1 | 从 metrics.json 填 |

## 10. 常见问题

- 下载预训练权重失败：使用 `--no-pretrained`，或提前缓存 torchvision 权重。
- `CUDA out of memory`：降低 batch size，终止残留进程，确认没有同时运行评估。
- 指标异常高：检查地理区域泄漏和标签是否被当作输入。
- 指标接近零：检查 A/B/label 是否同名、标签是 0/255、时相是否错位。
- 本地仍显示启发式引擎：检查 ONNX 路径、依赖和健康接口启动日志。
