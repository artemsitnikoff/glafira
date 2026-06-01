import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

// Назначение/снятие тега кандидату. Сами теги создаются/правятся в Настройках.
export function useAddCandidateTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ candidateId, tagId }: { candidateId: string; tagId: string }) => {
      await api.post(`/candidates/${candidateId}/tags`, { tag_id: tagId })
    },
    onSuccess: (_d, { candidateId }) => {
      qc.invalidateQueries({ queryKey: ['candidates', candidateId] })
      qc.invalidateQueries({ queryKey: ['candidates'] })
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.invalidateQueries({ queryKey: ['tags'] }) // usage_count меняется
    },
  })
}

export function useRemoveCandidateTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ candidateId, tagId }: { candidateId: string; tagId: string }) => {
      await api.delete(`/candidates/${candidateId}/tags/${tagId}`)
    },
    onSuccess: (_d, { candidateId }) => {
      qc.invalidateQueries({ queryKey: ['candidates', candidateId] })
      qc.invalidateQueries({ queryKey: ['candidates'] })
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.invalidateQueries({ queryKey: ['tags'] })
    },
  })
}
