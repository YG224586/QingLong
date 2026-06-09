# chinaUnicom 云盘图片候选缺失处理记录

## 问题现象

执行云盘乘风活动时提示无候选图片。排查后确认不是分页、clientId 或脚本筛选偶发问题，而是目标账号云盘里没有 `jpg/jpeg/png` 图片候选。

对比思路：

- 源账号：活动图片列表能查到图片候选。
- 目标账号：活动图片列表为空。
- 目标账号根目录：只有活动视频、任务文本或其它任务文件，无图片。

处理结果：从源账号云盘读取一张图片，下载原图后用目标账号云盘 token 上传到目标账号根目录。上传接口可能读超时，但服务端可能已经落盘，最终以目标账号图片列表复查结果为准。

## 脚本修复点

- 增加文件类 dispatcher 地址：`https://s.pan.wo.cn/wohome/dispatcher`。
- 增加云盘参数 AES-CBC 加密方法。
- 文件类 dispatcher 请求使用 App 同款 headers，body 只带 `param`。
- 无候选图片时明确提示用户上传一张清晰单人正脸图片到联通云盘。

## 关键接口链路

### 获取云盘 token

先通过联通入口 ticket 换取云盘 token：

1. `getTicketByNative`
2. `HandheldHallAutoLoginV2`

后续查询、下载 URL 生成、上传都依赖目标账号自己的云盘 token。

### 云盘 dispatcher 参数加密

- AES-CBC
- key：`str(token).ljust(16)[:16]`
- iv：`wNSOYIB1k1DjY5lA`
- padding：PKCS7
- 输出：base64

### 查询活动图片候选

活动 H5 图片列表用于判断能否参与制作：

```python
payload = {
    "pageSize": 50,
    "pageNo": 1,
    "suffixList": ["jpg", "jpeg", "png"],
    "fileType": "1",
    "spaceType": 0,
    "sortRule": "0",
}
```

接口：

```text
POST /wohome/knowledge/queryTypeFileList
```

### 查询真实云盘文件

活动图片列表返回的 `fid` 不一定能直接下载。需要用底层文件树查真实文件记录：

```text
dispatcher key: QueryAllFiles
```

核心参数：

```python
{
    "clientId": "1001000035",
    "spaceType": "0",
    "sortRule": "0",
    "parentDirectoryId": "0",
    "pageNum": "0",
    "pageSize": 500,
}
```

### 生成下载 URL

用真实文件记录里的 `fid` 生成下载地址：

```text
dispatcher key: GetDownloadUrlV2
```

核心参数：

```python
{
    "type": "1",
    "fidList": [real_fid],
    "clientId": "1001000035",
}
```

解密 `RSP.DATA` 后取：

```python
download_url = data["list"][0]["downloadUrl"]
```

### 上传到目标账号

接口：

```text
POST https://tjupload.pan.wo.cn/openapi/client/upload2C
```

核心 form：

```python
file_info = {
    "spaceType": "0",
    "directoryId": "0",
    "batchNo": batch_no,
    "fileName": file_name,
    "fileSize": len(content),
    "fileType": "1",
}
form = {
    "uniqueId": unique_id,
    "accessToken": target_token,
    "fileName": file_name,
    "psToken": "undefined",
    "fileSize": str(len(content)),
    "totalPart": "1",
    "channel": "wocloud",
    "directoryId": "0",
    "fileInfo": encrypt(file_info, target_token),
    "partSize": str(len(content)),
    "partIndex": "1",
}
```

上传后再次调用 `queryTypeFileList`，确认目标账号能查到图片候选。

## 下次处理路线

### 路线A：让用户提供照片

适合只有一个账号，或没有其它账号可借图。

1. 让用户提供一张清晰单人正脸照片，建议 `jpg/jpeg/png`，小于 `10MB`。
2. 用目标账号 CK 初始化登录并获取云盘 token。
3. 读取用户提供的本地图片 bytes。
4. 调 `upload2C` 上传到目标账号根目录。
5. 复查 `queryTypeFileList`，确认出现图片候选。

### 路线B：从另一个账号读取图片再上传

适合其它账号云盘已有可用图片。

1. 初始化源账号和目标账号。
2. 源账号用 `queryTypeFileList` 找图片候选。
3. 源账号用 `QueryAllFiles` 找同名真实文件记录，取真实 `fid`。
4. 源账号用 `GetDownloadUrlV2` 生成下载 URL。
5. 下载图片 bytes。
6. 目标账号用 `upload2C` 上传。
7. 复查目标账号 `queryTypeFileList`。

## 已验证失败路径

- 直接把另一个账号的图片 `fid` 传给活动转存接口，可能返回业务错误。
- 用视频保存接口保存图片，可能返回内容错误或触发限流。
- 直接用活动图片列表里的 `fid` 请求临时下载，可能 404。

## 发帖注意

- 不要贴 CK、token、手机号、青龙地址、本地路径。
- 不要贴真实账号序号、真实文件名、真实图片链接。
- 不要把其它账号的 FID 固定进脚本，单账号场景不可用。
- 上传后以目标账号 `queryTypeFileList` 是否能看到图片为准。
- 测试时需要禁用代理只能用进程环境变量，不要写进脚本，也不要改系统全局代理。
