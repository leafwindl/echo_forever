# Echo COS 对象存储配置

## 当前状态

- Bucket：`echo-1438300232`
- Region：`ap-guangzhou`
- Bucket 保持私有读。
- 图片生成未启动：`LETTER_IMAGE_GENERATION_ENABLED=false`。
- `img.echoaiforever.cn` 没有 HTTPS 证书前，`COS_CUSTOM_DOMAIN` 必须留空。
- 当前聊天、语音和表情包继续使用原有存储链路，不受 COS 配置影响。

## 服务器配置位置

生产环境只编辑服务器文件：

```text
/opt/echo/app/Echo-backend/.env
```

填写以下字段：

```dotenv
COS_ENABLED=true
COS_BUCKET=echo-1438300232
COS_REGION=ap-guangzhou
COS_SECRET_ID=在腾讯云 CAM 获取
COS_SECRET_KEY=在腾讯云 CAM 获取
COS_REUSE_TENCENT_CREDENTIALS=false
COS_CUSTOM_DOMAIN=
COS_PRIVATE_READ=true
COS_OBJECT_PREFIX=echo
COS_SIGNED_URL_EXPIRES_SECONDS=900
COS_TIMEOUT_SECONDS=30

LETTER_IMAGE_GENERATION_ENABLED=false
```

不要把 `COS_SECRET_ID`、`COS_SECRET_KEY` 写入 Flutter、提交到 Git，或发送到聊天中。

## 获取专用密钥

1. 登录腾讯云控制台，进入“访问管理 CAM”。
2. 创建一个仅供 Echo 后端使用的子用户，例如 `echo-backend-cos`。
3. 只开启编程访问，不为该子用户创建控制台登录密码。
4. 在“策略 > 新建自定义策略 > 按策略语法创建”中创建下面的最小权限策略，并关联给该子用户。
5. 在该子用户的“API 密钥”页面新建密钥，取得 `SecretId` 和 `SecretKey`。
6. 将两个值直接填写到服务器 `.env`，不要填写到 `.env.example`。

策略内容：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "cos:PutObject",
        "cos:GetObject",
        "cos:HeadObject",
        "cos:DeleteObject"
      ],
      "resource": [
        "qcs::cos:ap-guangzhou:uid/1438300232:echo-1438300232/echo/*"
      ]
    }
  ]
}
```

这组权限只允许后端在当前 Bucket 的 `echo/` 前缀下上传、读取、查看元数据和删除对象，不能修改 Bucket 配置，也不能访问其他 Bucket。

不要使用云服务器密码、腾讯云登录密码、CosyVoice Key 或 Flutter 中的配置代替 COS 密钥。现有 `TENCENT_SECRET_ID/TENCENT_SECRET_KEY` 用于 ASR；即使技术上可能具备 COS 权限，也不要自动复用。

当前过渡阶段允许显式复用 ASR 密钥：

```dotenv
COS_SECRET_ID=
COS_SECRET_KEY=
COS_REUSE_TENCENT_CREDENTIALS=true
```

以后取得专用 COS 密钥后，填写 `COS_SECRET_ID/COS_SECRET_KEY` 并把回退开关改为 `false`。专用 COS 密钥始终优先，代码不会把一半 COS 密钥和一半 ASR 密钥混合使用。

## 连通性验证

更新依赖并执行一次完整的上传、签名下载和删除测试：

```bash
cd /opt/echo/app
docker compose build echo-backend
docker compose run --rm echo-backend python /app/scripts/cos_storage.py smoke-test
```

如果容器没有挂载仓库根目录的 `scripts/`，改用后端容器内 Python 或在宿主机执行：

```bash
cd /opt/echo/app
uv run python scripts/cos_storage.py smoke-test
```

成功时只输出 Bucket 和临时对象 key；测试对象随后会自动删除，不会打印签名 URL 或密钥。

## 上传 Echo 参考图

连通性测试通过后，可以把现有人物素材上传到私有 Bucket：

```bash
cd /opt/echo/app
uv run python scripts/cos_storage.py upload-reference-assets
```

对应对象 key：

```text
echo/reference/character/echo-idle-v1.png
echo/reference/character/echo-sit-v1.png
```

这一步只保存参考图，不会启动图片生成任务。等图片服务商确定后，再由每日来信 Worker 读取参考图并上传生成结果。

## 自定义域名启用条件

在 `img.echoaiforever.cn` 已绑定有效 HTTPS 证书后，才能修改为：

```dotenv
COS_CUSTOM_DOMAIN=https://img.echoaiforever.cn
```

随后重启后端并重新运行 smoke test。没有证书时保持空值，SDK 会使用腾讯云 COS 默认 HTTPS 域名。
