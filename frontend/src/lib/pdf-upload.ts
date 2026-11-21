import { formatFileSize } from './utils'

export function validatePdfFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
    return '仅支持 PDF 文件。'
  }
  if (file.size > 20 * 1024 * 1024) {
    return `文件 ${formatFileSize(file.size)} 超过 20MB 上限。`
  }
  if (file.size === 0) return '文件内容为空。'
  return null
}
