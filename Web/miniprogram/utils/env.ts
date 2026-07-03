export type MiniProgramEnvironment = 'develop' | 'trial' | 'release';

interface AppEnvironmentConfig {
  apiBaseUrl: string;
}

const ENVIRONMENT_CONFIGS: Record<MiniProgramEnvironment, AppEnvironmentConfig> = {
  develop: {
    apiBaseUrl: 'http://127.0.0.1:8000',
  },
  trial: {
    apiBaseUrl: 'https://staging-api.example.com',
  },
  release: {
    apiBaseUrl: 'https://api.example.com',
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
