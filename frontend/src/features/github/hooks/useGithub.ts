import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { githubApi } from '../api/githubApi'
import { toast } from '@/shared/hooks/useToast'

export const useGitIntegration = (projectId: string) =>
  useQuery({
    queryKey: ['github-integration', projectId],
    queryFn: () => githubApi.getIntegration(projectId),
    enabled: !!projectId,
    // 404 means not connected — treat as null, don't retry
    retry: false,
  })

export const useInitiateGitHubInstall = (projectId: string) =>
  useMutation({
    mutationFn: () => githubApi.getInstallUrl(projectId),
    onSuccess: ({ install_url }) => {
      window.location.href = install_url
    },
    onError: () => toast('Failed to initiate GitHub connection', 'error'),
  })

export const useDeleteGitIntegration = (projectId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => githubApi.deleteIntegration(projectId),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ['github-integration', projectId] })
      toast('GitHub disconnected', 'success')
    },
    onError: () => toast('Failed to disconnect GitHub', 'error'),
  })
}