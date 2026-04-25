# Image Runtime Environment Contract

`004-phase3-image-ingest` 新增的 runtime env：

| Env | 預設 | 說明 |
|---|---|---|
| `HKS_IMAGE_TIMEOUT_SEC` | `30` | 單檔 image ingest timeout |
| `HKS_IMAGE_MAX_FILE_MB` | `20` | 單檔 image 原始檔大小上限 |
| `HKS_IMAGE_MAX_PIXELS` | `100000000` | decode 後像素總量上限 |
| `HKS_OCR_LANGS` | `eng+chi_tra` | tesseract language set，缺少對應 traineddata 時視為 misconfiguration |

不新增 `--vlm` 旗標；VLM 不在 `004` 範圍。
