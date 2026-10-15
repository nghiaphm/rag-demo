export async function copyText(text: string, clipboard?: Pick<Clipboard, "writeText">) {
  if (!clipboard) throw new Error("Clipboard unavailable")
  await clipboard.writeText(text)
}
