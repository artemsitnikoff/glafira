import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

// Локальный тип (openapi не регенерён)
export interface MessageTemplateOut {
  id: string
  company_id: string
  name: string
  body: string
  order_index: number
  created_at: string
  updated_at: string
}

export function useMessageTemplates() {
  return useQuery({
    queryKey: ['message-templates'],
    queryFn: async () => {
      const response = await api.get('/message-templates')
      return response.data as MessageTemplateOut[]
    },
  })
}