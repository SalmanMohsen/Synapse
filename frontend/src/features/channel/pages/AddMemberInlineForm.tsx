import { useState } from 'react'
import { Modal, SelectField, Btn, UserSearchField } from '@/shared/components'
import type { User } from '@/features/auth/types/auth.types'


export function AddMemberInlineForm({
  roles,
  onAdd,
  onClose,
  loading,
  scopeKey, // <-- Add this
  searchFn, // <-- Add this
}: {
  roles: { value: string; label: string }[]
  onAdd: (userId: string, role: string) => Promise<void>
  onClose: () => void
  loading: boolean
  scopeKey: string                         // <-- Add this
  searchFn: (q: string) => Promise<User[]> // <-- Add this
}) {
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [role, setRole] = useState(roles[0]?.value ?? 'member')
  const [err, setErr] = useState('')

  const handleAdd = async () => {
    if (!selectedUser) { setErr('Please select a user'); return }
    await onAdd(selectedUser.id, role)
  }

  return (
    <Modal
      title="Add member"
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={handleAdd} loading={loading}>Add</Btn>
        </>
      }
    >
      <UserSearchField
        label="User"
        selectedUser={selectedUser}
        onSelect={(user) => { setSelectedUser(user); setErr('') }}
        scopeKey={scopeKey} // <-- Pass down
        searchFn={searchFn} // <-- Pass down
        error={err}
      />
      <SelectField label="Role" value={role} onChange={setRole} options={roles} />
    </Modal>
  )
}