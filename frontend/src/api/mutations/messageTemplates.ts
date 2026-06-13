import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { MessageTemplateOut } from '@/api/hooks/useMessageTemplates'

export interface MessageTemplateInput {
  name: string
  body: string
  order_index?: number
}

export function useCreateMessageTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: MessageTemplateInput): Promise<MessageTemplateOut> => {
      const r = await api.post('/message-templates', data)
      return r.data as MessageTemplateOut
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['message-templates'] })
    },
  })
}

export function useUpdateMessageTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string } & Partial<MessageTemplateInput>): Promise<MessageTemplateOut> => {
      const r = await api.patch(`/message-templates/${id}`, data)
      return r.data as MessageTemplateOut
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['message-templates'] })
    },
  })
}

export function useDeleteMessageTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/message-templates/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['message-templates'] })
    },
  })
}