// utils/api.ts
export const BASE_URL = 'https://impotent-jersey-hurler.ngrok-free.dev'
// 前后端通信接口封装层
export function login(code: string, clientId: string): Promise<{ user_id: string }> { //将微信登陆获取的code发送给后端获取openid
  // Promise是用于处理异步操作的对象，代表未来会完成的任务。
  return new Promise((resolve, reject) => { 
    wx.request({
      url: `${BASE_URL}/login`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' }, //请求头
      // client_id 是本地开发兜底身份：后端没有微信密钥时，用它生成稳定 dev 用户。
      data: { code, client_id: clientId },
      success: (res: any) => { //请求成功时的回调函数
        if (res.statusCode === 200 && res.data.user_id) {
          resolve(res.data);
        } else {
          reject(res.data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

//发送消息给后端
export function sendMessage(userId: string, message: string): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/chat/send`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { user_id: userId, message },
      success: (res: any) => {
        if (res.statusCode === 200 && res.data.reply) {
          resolve(res.data.reply);
        } else {
          reject(res.data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}
