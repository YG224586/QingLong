// 当前脚本来自于http://script.345yun.cn脚本库下载！

// 喜马拉雅自动签到脚本
// 支持自动签到和Cookie更新
// 亓分享
// 

const KEY_COOKIE = '完整 Cookie'
const KEY_TOKEN = '从 Cookie 提取的 token（或单独保存）'
const KEY_USERID = '用户 ID'
const KEY_LAST_SIGN = '上次签到日期（用于去重）'
const KEY_DEVICE_ID = '设备 ID（无则生成）'

// 主函数
async function main() {
    // 获取存储的Cookie和Token
    const cookie = $persistentStore.read(KEY_COOKIE)
    const token = $persistentStore.read(KEY_TOKEN)
    const userId = $persistentStore.read(KEY_USERID)
    const deviceId = $persistentStore.read(KEY_DEVICE_ID) || generateDeviceId()

    if (!cookie || !token || !userId) {
        $notification.post('喜马拉雅签到', '失败', '未找到认证信息，请打开喜马拉雅小程序')
        return
    }

    // 检查今日是否已签到
    const lastSignDate = $persistentStore.read(KEY_LAST_SIGN)
    const today = new Date().toDateString()
    if (lastSignDate === today) {
        $notification.post('喜马拉雅签到', '跳过', '今日已签到过')
        return
    }

    try {
        // 执行签到
        const signResult = await performSignIn(cookie, token, userId, deviceId)

        if (signResult.code === 0) {
            // 签到成功
            $persistentStore.write(today, KEY_LAST_SIGN)
            $notification.post('喜马拉雅签到', '成功', `获得奖励: ${signResult.data.award.award_received_text}`)

            // 获取积分信息
            const integralResult = await getIntegral(cookie, token, userId, deviceId)
            if (integralResult.code === 10000) {
                $notification.post('喜马拉雅积分', `当前积分: ${integralResult.result.integral}`, '')
            }
        } else {
            $notification.post('喜马拉雅签到', '失败', `错误: ${signResult.msg}`)
        }
    } catch (error) {
        $notification.post('喜马拉雅签到', '错误', error.message || '未知错误')
    }
}

// 执行签到
async function performSignIn(cookie, token, userId, deviceId) {
    const timestamp = Date.now()
    const nonce = generateNonce()

    // 构建签名参数（需要根据实际算法调整）
    const signParams = {
        device_id: deviceId,
        sn: '11480_00_100480',
        version: '2.1',
        app_key: 'e23df0e3d21c4379bf2a5b302a843a25',
        device_id_type: 'UUID',
        version_code: '9094',
        product_type: 'child_watches_okii',
        client_os_type: '2',
        nonce: nonce,
        timestamp: timestamp,
        user_id: userId
    }

    // 生成签名（需要根据实际算法实现）
    const sig = generateSignature(signParams)
    signParams.sig = sig

    // 构建请求参数
    const formBody = Object.keys(signParams).map(key => 
        encodeURIComponent(key) + '=' + encodeURIComponent(signParams[key])
    ).join('&')

    return new Promise((resolve, reject) => {
        $httpClient.post({
            url: 'https://api.ximalaya.com/ximalayaos-smart-wear/api/parent_sign_in/sign_in',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Cookie': cookie,
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.63(0x18003f28) NetType/WIFI Language/zh_CN',
                'Referer': 'https://m.ximalaya.com/',
                'Origin': 'https://m.ximalaya.com'
            },
            body: formBody
        }, (error, response, data) => {
            if (error) {
                reject(error)
            } else {
                try {
                    resolve(JSON.parse(data))
                } catch (e) {
                    reject(e)
                }
            }
        })
    })
}

// 获取积分信息
async function getIntegral(cookie, token, userId, deviceId) {
    const timestamp = Date.now()
    const nonce = generateNonce()

    // 构建签名参数
    const signParams = {
        device_id: deviceId,
        sn: '11480_00_100480',
        version: '2.2',
        app_key: 'e23df0e3d21c4379bf2a5b302a843a25',
        device_id_type: 'UUID',
        version_code: '9093',
        product_type: 'child_watches_okii',
        client_os_type: '3',
        nonce: nonce,
        timestamp: timestamp,
        userId: userId
    }

    // 生成签名
    const sig = generateSignature(signParams)

    const url = `https://api.ximalaya.com/ximalayaos-smart-wear/api/integral/getUserIntegral?${Object.keys(signParams).map(key => 
        encodeURIComponent(key) + '=' + encodeURIComponent(signParams[key])
    ).join('&')}&sig=${encodeURIComponent(sig)}`

    return new Promise((resolve, reject) => {
        $httpClient.get({
            url: url,
            headers: {
                'Cookie': cookie,
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.63(0x18003f28) NetType/WIFI Language/zh_CN',
                'Referer': 'https://m.ximalaya.com/'
            }
        }, (error, response, data) => {
            if (error) {
                reject(error)
            } else {
                try {
                    resolve(JSON.parse(data))
                } catch (e) {
                    reject(e)
                }
            }
        })
    })
}

// HTTP请求处理（用于抓取Cookie和Token）
function handleHTTPRequest(request) {
    // 只处理喜马拉雅API请求
    if (request.url.includes('api.ximalaya.com')) {
        // 获取请求头中的Cookie
        const cookie = request.headers['Cookie'] || request.headers['cookie']
        if (cookie && cookie.includes('_token')) {
            // 提取Token
            const tokenMatch = cookie.match(/_token=([^&;]+)/)
            if (tokenMatch && tokenMatch[1]) {
                $persistentStore.write(tokenMatch[1], KEY_TOKEN)

                // 尝试从Token中提取用户ID
                const userIdMatch = tokenMatch[1].match(/(\d+)/)
                if (userIdMatch && userIdMatch[1]) {
                    $persistentStore.write(userIdMatch[1], KEY_USERID)
                }
            }

            // 保存完整Cookie
            $persistentStore.write(cookie, KEY_COOKIE)

            // 生成设备ID并保存
            const deviceId = generateDeviceId()
            $persistentStore.write(deviceId, KEY_DEVICE_ID)
        }
    }

    // 继续原始请求
    return request
}

// HTTP响应处理
function handleHTTPResponse(response) {
    // 可以在这里处理响应，例如检查是否认证过期
    if (response.status === 401 || response.status === 403) {
        // 认证过期，清除保存的认证信息
        $persistentStore.write('', KEY_COOKIE)
        $persistentStore.write('', KEY_TOKEN)
        $notification.post('喜马拉雅认证', '过期', '请重新打开喜马拉雅小程序以更新认证信息')
    }

    return response
}

// 生成随机设备ID
function generateDeviceId() {
    const randomStr = Math.random().toString(36).substring(2, 12)
    return `h5_${randomStr}_2.4.25`
}

// 生成随机Nonce
function generateNonce() {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    let nonce = ''
    for (let i = 0; i < 32; i++) {
        nonce += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    return nonce
}

// 生成签名（需要根据实际算法实现）
function generateSignature(params) {
    // 这里是签名算法的伪实现
    // 实际签名算法需要根据喜马拉雅的实际算法进行调整
    // 可能需要使用MD5、SHA1或其他哈希算法

    // 示例：将参数按key排序后拼接成字符串，然后进行MD5哈希
    const sortedKeys = Object.keys(params).sort()
    let signStr = ''

    for (const key of sortedKeys) {
        signStr += key + params[key]
    }

    // 添加密钥（如果有）
    signStr += 'your_secret_key'

    // 返回模拟签名（实际需要实现正确的哈希算法）
    return md5(signStr)
}

// MD5哈希函数（示例实现）
function md5(str) {
    // 这是一个简单的MD5实现示例
    // 在实际使用中，可能需要使用更完整的MD5实现
    let hash = 0
    if (str.length === 0) return hash.toString()
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i)
        hash = (hash << 5) - hash + char
        hash = hash & hash // Convert to 32bit integer
    }
    return hash.toString()
}

// 模块导出
if (typeof $argument !== 'undefined') {
    // 脚本被调用时执行
    main()
}

if (typeof $request !== 'undefined') {
    // HTTP请求处理
    const modifiedRequest = handleHTTPRequest($request)
    $done(modifiedRequest)
}

if (typeof $response !== 'undefined') {
    // HTTP响应处理
    const modifiedResponse = handleHTTPResponse($response)
    $done(modifiedResponse)
}
// 当前脚本来自于http://script.345yun.cn脚本库下载！