export function concatBytes(parts: Uint8Array[]): Uint8Array {
  const length = parts.reduce((sum: number, part: Uint8Array) => sum + part.length, 0);
  const result = new Uint8Array(length);
  let offset = 0;
  parts.forEach((part: Uint8Array) => { result.set(part, offset); offset += part.length; });
  return result;
}

export function hexBytes(hex: string): Uint8Array {
  const padded = hex.length % 2 ? `0${hex}` : hex;
  const result = new Uint8Array(padded.length / 2);
  for (let index = 0; index < result.length; index++) result[index] = parseInt(padded.substring(index * 2, index * 2 + 2), 16);
  return result;
}

export function bytesHex(bytes: Uint8Array): string {
  let result = '';
  bytes.forEach((byte: number) => result += byte.toString(16).padStart(2, '0'));
  return result;
}

// Same complemented CRC-16/CCITT and little-endian trailer as BlufiCRC.java.
export function blufiCrc(bytes: Uint8Array): number {
  let crc = 0xffff;
  bytes.forEach((byte: number) => {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) crc = ((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0)) & 0xffff;
  });
  return (~crc) & 0xffff;
}

export function frameBlufi(
  type: number, sequence: number, plain: Uint8Array, encrypted: Uint8Array | undefined,
  checksum: boolean, fragmented: boolean, requireAck: boolean = false
): Uint8Array {
  const frame = (encrypted ? 1 : 0) | (checksum ? 2 : 0) | (fragmented ? 16 : 0) | (requireAck ? 8 : 0);
  const header = new Uint8Array([type, frame, sequence, plain.length]);
  const body = encrypted ?? plain;
  if (!checksum) return concatBytes([header, body]);
  const crc = blufiCrc(concatBytes([new Uint8Array([sequence, plain.length]), plain]));
  return concatBytes([header, body, new Uint8Array([crc & 255, crc >> 8])]);
}
