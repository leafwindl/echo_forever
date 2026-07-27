type CharacterPose = 'idle' | 'sit';

const POSE_IMAGES: Record<CharacterPose, string> = {
  idle: '/assets/images/echo_idle.webp',
  sit: '/assets/images/idle_sit.webp',
};

Component({
  properties: {
    chatExpanded: {
      type: Boolean,
      value: false,
      observer() {
        this.updatePose();
      },
    },
    sitCrop: {
      type: Object,
      value: {},
    },
  },

  data: {
    activeAnimationSrc: POSE_IMAGES.idle,
  },

  lifetimes: {
    attached() {
      this.updatePose();
    },
  },

  methods: {
    updatePose() {
      const pose: CharacterPose = this.data.chatExpanded ? 'sit' : 'idle';
      this.setData({ activeAnimationSrc: POSE_IMAGES[pose] });
    },
  },
});
