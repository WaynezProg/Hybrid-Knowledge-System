# Dependency Map

A 專案延遲會影響 checkout service 與 notification service。

因為 checkout service 依賴 A 專案提供的 pricing API，
notification service 依賴 A 專案產出的事件流。
