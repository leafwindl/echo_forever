import { login, sendMessage } from '../../utils/api'; // 导入两个异步函数
import { BASE_URL } from '../../utils/api';

// 定义消息对象的结构：每个消息由唯一数字ID、发送者、文本内容
interface Message {
  id: number;
  sender: 'user' | 'echo';
  content: string;
}

let recorderManager: WechatMiniprogram.RecorderManager; //指定变量的类型

// 小程序的页面通过Page()构造器定义，接收一个包含数据、生命周期、事件处理函数的对象。也就是核心处理逻辑
Page({
  data: {
    messages: [] as Message[], // 存储显示的消息列表
    inputText: '',  //当前输入框的文本
    isThinking: false, // 是否显示AI正在输入的状态
    lastMsgId: '', // 滚动定位最新的消息的DOM ID
    msgIdCounter: 0, // 自增计数器，为消息生成唯一ID
    userId: '', //登陆成功后后端返回的用户ID
    isRecording: false,      // 是否正在录音
    recordStartTime: 0,      // 录音开始时间戳（用于防抖）
    shouldUploadVoice: false,   // 默认不上传
    chatExpanded: false, //扩展聊天框
  },

  onLoad() {
    // 微信登录获取 user_id
    wx.login({ 
      success: async (res) => { //从微信官方获取一次性code，async声明异步函数
        try {
          const result = await login(res.code);  //将code传给自定义login函数（api.ts），返回user_id
          // 只有当login函数成功后才会进行这一步
          this.setData({ userId: result.user_id }); //将user.id存入user ID的页面数据中。this指向当前页面的实例（Page对象）
          // 登录成功后发一条 Echo 开场白（可以从后端获取，这里先固定）
          this.addMessage('echo', '嗨，我是 Echo，很开心认识你。你可以告诉我你希望我怎么称呼你吗？');
        } catch (e) {
          console.error('登录失败', e);
          // 降级：使用临时 ID，保证可以聊天
          this.setData({ userId: 'guest' });
          this.addMessage('echo', '嗨，我是 Echo，很高兴认识你～');
        }
      },
      fail: () => {
        this.setData({ userId: 'guest' });
        this.addMessage('echo', '嗨，我是 Echo，很高兴认识你～');
      }
    });
    
    recorderManager = wx.getRecorderManager(); //获取全局唯一的录音管理器实例
    this.initRecorderEvents();
  },

  onToggleChatExpand() {
    this.setData({
      chatExpanded: !this.data.chatExpanded
    });
  },

  initRecorderEvents() {
    // 监听录音开始
    recorderManager.onStart(() => { // 这个箭头函数只会在录音开始的时候被调用，只是一个监听器，当被触发后会按照箭头函数内执行
      console.log('录音开始');
      this.setData({ isRecording: true });
      wx.showToast({ title: '录音中... 松开结束', icon: 'none', duration: 60000 });
    });

    // 监听录音结束，拿到临时文件路径
    recorderManager.onStop((res) => {
      console.log('录音结束', res);
      const should = this.data.shouldUploadVoice;
      this.setData({ isRecording: false, shouldUploadVoice: false });
      wx.hideToast();
      if (should && res.tempFilePath) {
        this.uploadVoice(res.tempFilePath);
      } else {
        wx.showToast({ title: '录音失败', icon: 'none' });
      }
    });

    // 监听录音错误
    recorderManager.onError((err) => {
      console.error('录音错误', err);
      this.setData({ isRecording: false });
      wx.hideToast();
      wx.showToast({ title: '录音失败，请重试', icon: 'none' });
    });
  },

  onInput(e: WechatMiniprogram.Input) { //事件绑定到输入框中
    this.setData({ inputText: e.detail.value }); //实时更新输入框的内容：形成打一个字然后出现在输入框上的效果
  },

  onSend() { //绑定到发送按钮的事件
    const text = this.data.inputText.trim(); //去除首尾空格
    if (!text || !this.data.userId) return;

    // 对话框中显示用户消息
    this.addMessage('user', text);
    this.setData({ inputText: '' });

    // 调用真实后端
    this.setData({ isThinking: true }); //触发界面显示“对方正在输入”
    sendMessage(this.data.userId, text) //异步请求后端AI回复
      .then((reply: string) => {
        this.addMessage('echo', reply); //返回回复内容文本
        this.setData({ isThinking: false }); //关闭思考
      })
      .catch((err) => {
        console.error('发送消息失败', err);
        this.addMessage('echo', '（抱歉，我暂时有点卡，请稍后再试）');
        this.setData({ isThinking: false });
      });
  },

  // 添加一条消息到列表
  addMessage(sender: 'user' | 'echo', content: string) {
    const id = this.data.msgIdCounter + 1; //自增ID，记录每句话的ID数量
    const newMsg: Message = { id, sender, content }; // 创建新消息对象，id、发送者、文本内容
    const messages = [...this.data.messages, newMsg]; // 拼接到消息后面
    this.setData({ //通过SetData更新
      messages,
      msgIdCounter: id,
      lastMsgId: `msg-${id}`, //（值设为 msg-${id}，配合 scroll-into-view 自动滚动到底部）
    });
  },

  onClearContext() {
    // 临时清空前端消息列表（后端上下文还会保留）
    this.setData({ messages: [] });
    wx.showToast({ title: '上下文已清除', icon: 'none' });
  },

  async onStartRecord() {
    // 检查录音权限
    const auth = await this.checkRecordAuth();
    if (!auth) return;

    this.setData({ shouldUploadVoice: true });
  
    // 开始录音配置（PCM 格式，16kHz 单声道，适合 ASR），
    recorderManager.start({ //这个是一个触发信号，成功后会执行OnStart的箭头函数
      duration: 60000,          // 最长 60 秒
      sampleRate: 16000,
      numberOfChannels: 1,
      format: 'mp3',            // 或者 'mp3'，根据后端需求
      // frameSize: 5              // 每录制5KB的音频数就触发一次回调，拿到小段“分片数据”，以满足后续流式的效果
    });
  },

  onStopRecord() {
    if (!this.data.isRecording) return;
    recorderManager.stop();
  },

  onCancelRecord() {
    if (!this.data.isRecording) return;
    this.setData({ shouldUploadVoice: false }); 
    recorderManager.stop();      // 取消上传
  },

  checkRecordAuth(): Promise<boolean> {
    return new Promise((resolve) => {
      wx.getSetting({ // 获取当前授权状态
        success: (res) => {
          if (res.authSetting['scope.record']) { // 判断录音权限
            resolve(true);
          } else {
            wx.authorize({ //请求录音权限
              scope: 'scope.record',
              success: () => resolve(true),
              fail: () => {
                wx.showModal({
                  title: '提示',
                  content: '需要录音权限，请在设置中开启',
                  success: () => wx.openSetting()
                });
                resolve(false);
              }
            });
          }
        }
      });
    });
  },

  uploadVoice(filePath: string) {
    wx.showLoading({ title: '识别中...' });

    // 第 1 步：仅上传给 /voice/asr 进行语音识别
    wx.uploadFile({
      url: `${BASE_URL}/voice/asr`,
      filePath: filePath,
      name: 'audio',
      header: { 'Content-Type': 'multipart/form-data' },
      success: (res) => {
        wx.hideLoading();
        if (res.statusCode === 200) {
          const asrData = JSON.parse(res.data);
          const userText = asrData.user_text;

          if (!userText) {
            wx.showToast({ title: '未听清，请重试', icon: 'none' });
            return;
          }

          // ★ 立刻将用户的语音内容展示在屏幕上！
          this.addMessage('user', userText);

          // 显示 AI 正在思考的状态
          this.setData({ isThinking: true });

          // 第 2 步：拿着识别出的话去请求 /voice/reply 获取回复和音频
          wx.request({
            url: `${BASE_URL}/voice/reply`,
            method: 'POST',
            data: {
              user_id: this.data.userId || 'test_user_001',
              message: userText
            },
            success: (replyRes: any) => {
              this.setData({ isThinking: false });
              if (replyRes.statusCode === 200) {
                const replyData = replyRes.data;
                
                // ★ AI 文字回复上屏！
                if (replyData.reply) {
                  this.addMessage('echo', replyData.reply);
                }

                // ★ 播报 AI 的语音
                if (replyData.audio_url) {
                  this.playVoice(replyData.audio_url);
                }
              }
            },
            fail: (err) => {
              this.setData({ isThinking: false });
              console.error('获取AI回复失败', err);
              this.addMessage('echo', '（抱歉，我暂时有点卡，请稍后再试）');
            }
          });

        } else {
          wx.showToast({ title: '语音识别失败', icon: 'none' });
        }
      },
      fail: (err) => {
        wx.hideLoading();
        console.error('上传录音失败', err);
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  },

  // 播放音频
  playVoice(url: string) {
    const innerAudio = wx.createInnerAudioContext();
    innerAudio.src = url;
    innerAudio.autoplay = true;
    innerAudio.onError((err) => {
      console.error('播放失败', err);
      wx.showToast({ title: '播放失败', icon: 'none' });
    });
  }
});