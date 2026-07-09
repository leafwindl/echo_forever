export type MiniProgramEnvironment = 'develop' | 'trial' | 'release';

interface AppEnvironmentConfig {
  apiBaseUrl: string;
  adminDebugEnabled: boolean;
  adminDebugToken: string;
}

const ENVIRONMENT_CONFIGS: Record<MiniProgramEnvironment, AppEnvironmentConfig> = {
  develop: {
    apiBaseUrl: 'https://api.echoaiforever.cn',
    adminDebugEnabled: true,
    adminDebugToken: 'change-me',
  },
  trial: {
    apiBaseUrl: 'https://api.echoaiforever.cn',
    adminDebugEnabled: true,
    adminDebugToken: 'change-me',
  },
  release: {
    apiBaseUrl: 'https://api.echoaiforever.cn',
    adminDebugEnabled: false,
    adminDebugToken: '',
  },
};

function getMiniProgramEnvironment(): MiniProgramEnvironment {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion;
  } catch (error) {
    void error;
    return 'develop';
  }
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

export function getAppConfig(): AppEnvironmentConfig {
  const environment = getMiniProgramEnvironment();
  const config = ENVIRONMENT_CONFIGS[environment];

  return {
    ...config,
    apiBaseUrl: trimTrailingSlash(config.apiBaseUrl),
  };
}

export const appConfig = getAppConfig();
