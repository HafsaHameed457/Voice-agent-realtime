export function int16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.length * 2)
  for (let i = 0; i < pcm.length; i++) {
    bytes[i * 2] = pcm[i] & 0xff
    bytes[i * 2 + 1] = (pcm[i] >> 8) & 0xff
  }
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export function base64ToUint8Array(b64: string): Uint8Array {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
}
