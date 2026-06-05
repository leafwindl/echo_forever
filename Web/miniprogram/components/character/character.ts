Component({
  properties: {
    chatExpanded: {
      type: Boolean,
      value: false,
    },
    sitCrop: {
      type: Object,
      value: {
        cropWidth: '750rpx',
        cropHeight: '300rpx',
        cropOffsetX: '0rpx',
        cropOffsetY: '0rpx',
        imageWidth: '1200rpx',
        imageLeft: '-225rpx',
        imageTop: '-420rpx',
      },
    },
  },
  methods: {
    // 可添加动画控制方法
  },
});
