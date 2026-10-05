# 第三方来源与使用条件

本项目原创程序代码及原创项目文档采用 [MIT License](LICENSE)。数据、第三方影像、预训练参数以及基于这些资料训练的模型权重不因源码开源而取得 MIT 授权。

## LEVIR-CD 与演示影像

- 原始数据集：[LEVIR-CD 官方页面](https://justchenhao.github.io/LEVIR/)。
- 原始论文：Hao Chen and Zhenwei Shi, *A Spatial-Temporal Attention-Based Method and a New Dataset for Remote Sensing Image Change Detection*, Remote Sensing, 2020, 12(10), 1662, [DOI: 10.3390/rs12101662](https://doi.org/10.3390/rs12101662)。
- 下载镜像：[ericyu/LEVIRCD_Cropped_256](https://huggingface.co/datasets/ericyu/LEVIRCD_Cropped_256)，固定提交 `70f91f6cc678c6c64516b37a48ec1374e2d52a5b`。镜像是下载途径，不能替代原始来源的使用条件。
- 仓库中的 `frontend/public/demo/before.png` 和 `after.png` 来自该裁剪版测试集样本 `001097`，用于研究演示；仓库不包含完整训练、验证或测试数据集。

官方说明原文："All images and annotations in LEVIR-CD can only be used for academic purposes, but are prohibited for any commercial use." 官方页面还要求遵守 Google Earth 使用条款。使用、复制或再分发相关影像前，请阅读官方页面及 [Google 地理内容使用指南](https://www.google.com/permissions/geoguidelines/)。本项目不将 LEVIR-CD 或这些示例图片标记为 MIT、CC BY 或其他通用开放许可，也不授予商业使用权。

## 训练权重

GitHub Release 提供的 `tianshan-sentinel-onnx-v1.0.0.zip` 包含在 LEVIR-CD 上训练的建筑变化检测模型与推理元数据。模型权重作为学术研究和教学复现材料发布，未获得独立的商业使用授权，不纳入本项目 MIT 源码许可；请同时遵守数据来源条件。发布权重不构成对基础影像及第三方参数的再授权。

模型编码器通过 torchvision 使用 ResNet18 预训练参数，来源与加载方式见 [torchvision ResNet18 文档](https://pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html)。相关软件和预训练参数的条件由各自来源决定。

## 软件依赖

FastAPI、Vue、PyTorch、torchvision、ONNX Runtime、OpenCV、ECharts、Lucide、ReportLab 等依赖保留各自版权与许可证。安装这些依赖时请查阅对应发行包中的许可文件；本项目的 MIT 许可不会替代第三方依赖的许可。
