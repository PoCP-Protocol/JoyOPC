# Listing media studio (compose, do not fork)

JoyOPC 上架包把三件开源设计收进自研运行时：

| 能力 | 开源来源 | JoyOPC 实现 |
|---|---|---|
| 渠道文案上限 | [open-listing-studio](https://github.com/clawnify/open-listing-studio) | `listing_limits.py` + Content Factory |
| 渠道主图画布 / 抠图可选 | [product_card_processor](https://github.com/Ouple/product_card_processor) + [rembg](https://github.com/danielgatis/rembg) | `media_studio.py` |
| Hook→Demo→Proof→CTA 分镜 | [AI-E-Commerce-Media-Studio](https://github.com/ronchen0927/AI-E-Commerce-Media-Studio) | `video_studio.py` |

不跑对方的 FastAPI/GPU 栈。无商品实拍时生成 **标明 synthetic** 的主图，不伪造实拍。Wan i2v / Replicate 默认关闭。`JOYOPC_REMBG=1` 且安装 rembg 后才做神经网络抠图。本机有 `ffmpeg` 才把分镜拼成 MP4。

```text
POST /api/content/pack/{master_product_id}
GET  /api/content/media/{sku}/{filename}
```
