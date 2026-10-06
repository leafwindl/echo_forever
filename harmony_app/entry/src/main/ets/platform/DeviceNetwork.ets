import http from '@ohos.net.http';

export interface DeviceAccessPoint {
  ssid: string;
  rssi: number;
  authMode: number;
}

export class DeviceNetwork {
  private async request(path: string, body?: Record<string, Object>): Promise<Record<string, Object>> {
    const client = http.createHttp();
    try {
      const response = await client.request(`http://192.168.4.1${path}`, {
        method: body === undefined && path === '/scan' ? http.RequestMethod.GET : http.RequestMethod.POST,
        header: { 'Content-Type': 'application/json' },
        extraData: body ? JSON.stringify(body) : undefined,
        connectTimeout: 5000, readTimeout: 35000
      });
      if (response.responseCode < 200 || response.responseCode >= 300) {
        throw new Error(`设备热点请求失败 HTTP ${response.responseCode}`);
      }
      return JSON.parse(String(response.result)) as Record<string, Object>;
    } finally {
      client.destroy();
    }
  }

  async scan(): Promise<DeviceAccessPoint[]> {
    const result = await this.request('/scan');
    const points: DeviceAccessPoint[] = [];
    if (Array.isArray(result.aps)) {
      result.aps.forEach((raw: Object) => {
        const value = raw as Record<string, Object>;
        const ssid = String(value.ssid ?? '');
        if (ssid) points.push({ ssid, rssi: Number(value.rssi ?? -100), authMode: Number(value.authmode ?? 0) });
      });
    }
    return points;
  }

  async configure(ssid: string, password: string): Promise<void> {
    const body: Record<string, Object> = {};
    body.ssid = ssid;
    body.password = password;
    const submitted = await this.request('/submit', body);
    if (submitted.success !== true) throw new Error(String(submitted.error ?? '设备连接 Wi-Fi 失败'));
    // The firmware starts its station connection only after /exit.
    const exited = await this.request('/exit', {});
    if (exited.success !== true) throw new Error(String(exited.error ?? '设备无法退出配网模式'));
  }
}
