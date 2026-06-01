import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { TagManage } from '@/api/hooks/useTags'

export interface TagInput {
  name: string
  color: string | null
}

export function useCreateTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: TagInput): Promise<TagManage> => {
      const r = await api.post('/settings/tags', data)
      return r.data as TagManage
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
    },
  })
}

export function useUpdateTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string } & Partial<TagInput>): Promise<TagManage> => {
      const r = await api.patch(`/settings/tags/${id}`, data)
      return r.data as TagManage
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
      // имя/цвет тега меняются — обновим карточки/списки, где он показан
      qc.invalidateQueries({ queryKey: ['candidates'] })
      qc.invalidateQueries({ queryKey: ['applications'] })
    },
  })
}

export function useDeleteTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/settings/tags/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
      // тег мог быть назначен кандидатам — обновим списки/карточки
      qc.invalidateQueries({ queryKey: ['candidates'] })
      qc.invalidateQueries({ queryKey: ['applications'] })
    },
  })
}
