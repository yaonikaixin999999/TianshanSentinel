# API 接口文档

基础地址：`http://localhost:8000/api/v1`

交互式文档：`http://localhost:8000/docs`

## 1. 服务与统计

- `GET /health`：返回服务状态、实际推理引擎和版本。
- `GET /statistics`：返回项目数、分析数、变化斑块、待复核数量、平均变化率和风险分布。

`engine` 是当前实际推理引擎，不应在前端硬编码。

## 2. 创建分析

`POST /analyses`，Content-Type 为 `multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| before | file | 是 | 前时相 PNG/JPEG/TIFF |
| after | file | 是 | 后时相 PNG/JPEG/TIFF |
| project_id | string | 否 | 监测项目 ID；省略时归入历史项目 |
| before_label | string | 否 | 前时相标签，默认 T1 |
| after_label | string | 否 | 后时相标签，默认 T2 |

返回结果包含影像 URL、模型引擎、变化率、置信度、不确定性、风险、时相标签、复核进度和变化斑块。每个斑块还包含规则型 `event_type` 建议和人工 `review_status`。

错误码：400 空文件或无效图像；404 项目不存在；413 文件过大；415 类型不支持；422 影像不可比较。

## 3. 分析与复核

- `GET /analyses?limit=50&project_id={id}`：分析列表；`project_id` 可选。
- `GET /analyses/{analysis_id}`：单次分析详情。
- `GET /reviews?status=pending|approved|rejected|all`：斑块复核队列。
- `PATCH /analyses/{analysis_id}/regions/{region_id}`：更新事件类型、复核状态和备注。

复核请求示例：

```json
{
  "event_type": "demolition",
  "event_label": "拆除清理",
  "review_status": "approved",
  "reviewer_note": "前后时相边界清晰"
}
```

## 4. 监测项目

- `GET /projects`：项目列表以及任务数、斑块数、待复核数和预警状态。
- `POST /projects`：创建项目。
- `PATCH /projects/{project_id}`：更新名称、区域、中心坐标、状态或预警阈值。
- `GET /projects/{project_id}/timeline`：按时间正序返回分析节点、变化率和斑块数。

项目创建请求示例：

```json
{
  "name": "新疆大学校园建设监测",
  "description": "校园建筑新增与拆除巡查",
  "area_name": "新疆大学",
  "center_lat": 43.77,
  "center_lon": 87.61,
  "alert_threshold": 0.12
}
```

## 5. 成果导出

- `GET /analyses/{analysis_id}/exports/report.docx`：Word 审计报告。
- `GET /analyses/{analysis_id}/exports/report.pdf`：PDF 定版报告。
- `GET /analyses/{analysis_id}/exports/regions.geojson`：变化斑块矢量。
- `GET /projects/{project_id}/exports/timeline.csv`：项目时间轴。

当上传影像没有地理参考信息时，GeoJSON 使用 `image_pixel` 坐标，并在文件内写入说明；不能把该坐标当作经纬度。

## 6. 版本策略

课程版 API 为 v1。新增可选字段不升级主版本；删除或改名字段应发布 `/api/v2`。图像 URL 是相对 URL，前端应与当前 API 域名组合。
