import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Category } from './api'

type Props = {
  categories: Category[]
  busy: boolean
  onCreate: (payload: { name: string; kind: Category['kind'] }) => Promise<boolean>
  onUpdate: (id: string, payload: { name?: string; active?: boolean }) => Promise<boolean>
}

export default function CategoryManager({ categories, busy, onCreate, onUpdate }: Props) {
  const [kind, setKind] = useState<Category['kind']>('EXPENSE')
  const [name, setName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (await onCreate({ name, kind })) setName('')
  }

  async function rename(category: Category) {
    if (!editingName.trim()) return
    if (await onUpdate(category.id, { name: editingName })) setEditingId(null)
  }

  return (
    <div className="stack">
      <section className="panel category-intro">
        <span className="eyebrow">CONTROLLED CLASSIFICATION</span>
        <h2>Income and expense categories</h2>
        <p>Categories keep reporting consistent. Deactivate one when it should no longer be offered to new transactions.</p>
      </section>
      <section className="split-forms category-layout">
        {(['INCOME', 'EXPENSE'] as const).map((categoryKind) => {
          const rows = categories.filter((category) => category.kind === categoryKind)
          return (
            <section className="panel category-group" key={categoryKind}>
              <div className="section-title">
                <div><span className="eyebrow">{categoryKind}</span><h2>{categoryKind === 'INCOME' ? 'Income' : 'Expense'}</h2></div>
                <span className="count">{rows.length}</span>
              </div>
              <div className="category-list">
                {rows.map((category) => (
                  <div className={`category-row ${category.active ? '' : 'inactive'}`} key={category.id}>
                    {editingId === category.id ? (
                      <form onSubmit={(event) => { event.preventDefault(); void rename(category) }}>
                        <input aria-label={`Rename ${category.name}`} value={editingName} onChange={(event) => setEditingName(event.target.value)} autoFocus />
                        <button className="text-button" disabled={busy}>Save</button>
                        <button type="button" className="text-button" onClick={() => setEditingId(null)}>Cancel</button>
                      </form>
                    ) : (
                      <>
                        <div><strong>{category.name}</strong><small>{category.active ? 'Available for new events' : 'Inactive; retained for history'}</small></div>
                        <div className="category-actions">
                          <button className="text-button" disabled={busy} onClick={() => { setEditingId(category.id); setEditingName(category.name) }}>Rename</button>
                          <button className="text-button" disabled={busy} onClick={() => void onUpdate(category.id, { active: !category.active })}>
                            {category.active ? 'Deactivate' : 'Enable'}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                ))}
                {!rows.length && <p className="empty">No categories yet.</p>}
              </div>
            </section>
          )
        })}
      </section>
      <form className="panel compact-form category-create" onSubmit={(event) => void create(event)}>
        <span className="eyebrow">NEW CATEGORY</span><h2>Add a preset</h2>
        <label>Name<input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} required placeholder="Electric Bill" /></label>
        <label>Type<select value={kind} onChange={(event) => setKind(event.target.value as Category['kind'])}><option value="EXPENSE">Expense</option><option value="INCOME">Income</option></select></label>
        <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Add category'}</button>
      </form>
    </div>
  )
}
