import { useEffect, useRef, useState } from 'react'
import {
  ActionIcon, Alert, Button, Checkbox, Group, Menu, Popover, ScrollArea, Text, TextInput, Tooltip,
} from '@mantine/core'
import {
  IconChevronDown, IconDeviceFloppy, IconDots, IconDownload, IconPencil, IconTrash, IconUpload,
} from '@tabler/icons-react'
import { INPUT } from './controls.jsx'

/*
 * Saved scenes of the open case, in the toolbar (openspec saved-views-train
 * D4; scenes-and-cameras A6-A10): the list behind a Scenes button, Save,
 * Export and Import beside it. Click a row to load it. A notice opens the list,
 * since that is where it shows.
 */

export function Scenes({
  views, notice, onDismiss, onSave, onLoad, onRename, onDelete, onExport, onImport,
}) {
  const fileRef = useRef(null)
  const [open, setOpen] = useState(false)
  // A row menu is a portal of its own, so a click in it reads as outside the list.
  const menuOpen = useRef(false)
  const names = views.scenes.map((s) => s.name)

  useEffect(() => { if (notice) setOpen(true) }, [notice])

  return (
    <Group gap={2} wrap="nowrap" data-ctl="scenes">
      <Popover opened={open} onChange={(o) => { if (o || !menuOpen.current) setOpen(o) }}
        position="bottom-end" width={240}
        withinPortal shadow="md">
        <Popover.Target>
          <Button size="xs" variant="subtle" color="gray" data-ctl="scenes-open"
            rightSection={<IconChevronDown size={14} stroke={1.8} />}
            onClick={() => setOpen((o) => !o)}>
            Scenes{names.length ? ` (${names.length})` : ''}
          </Button>
        </Popover.Target>
        <Popover.Dropdown p="xs" data-ctl="scenes-list">
          {views.scenes.length === 0 && (
            <Text size="xs" c="dimmed" data-ctl="scenes-empty">No saved scenes.</Text>
          )}
          <ScrollArea.Autosize mah={10 * 26}>
            {views.scenes.map((s) => (
              <SceneRow key={s.name} scene={s} names={names} menuOpen={menuOpen}
                onLoad={onLoad} onRename={onRename} onDelete={onDelete} />
            ))}
          </ScrollArea.Autosize>
          {notice && (
            <Alert color={notice.color} variant="light" withCloseButton onClose={onDismiss}
              p={6} mt={4} styles={{ message: { fontSize: 'var(--mantine-font-size-xs)' } }}
              data-ctl="views-notice">
              {notice.text}
            </Alert>
          )}
        </Popover.Dropdown>
      </Popover>
      <SaveScene names={names} onSave={onSave} />
      <Tooltip label="Export scenes and cameras to a file" openDelay={600}>
        <ActionIcon variant="subtle" size="md" onClick={onExport} data-ctl="views-export"
          aria-label="Export views">
          <IconDownload size={16} stroke={1.8} />
        </ActionIcon>
      </Tooltip>
      <Tooltip label="Import scenes and cameras from a file" openDelay={600}>
        <ActionIcon variant="subtle" size="md" onClick={() => fileRef.current?.click()}
          data-ctl="views-import" aria-label="Import views">
          <IconUpload size={16} stroke={1.8} />
        </ActionIcon>
      </Tooltip>
      <input
        ref={fileRef}
        type="file"
        accept=".json,application/json"
        hidden
        data-ctl="views-file"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) onImport(file)
        }}
      />
    </Group>
  )
}

function SaveScene({ names, onSave }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [withCamera, setWithCamera] = useState(false)
  const trimmed = name.trim()
  const exists = names.includes(trimmed)
  const save = () => {
    if (!trimmed) return
    onSave(trimmed, withCamera)
    setOpen(false)
  }

  return (
    <Popover opened={open} onChange={setOpen} position="bottom-end" withinPortal trapFocus>
      <Popover.Target>
        <Tooltip label="Save the current scene" openDelay={600}>
          <ActionIcon variant="subtle" size="md" data-ctl="scene-save" aria-label="Save scene"
            onClick={() => { setName(''); setWithCamera(false); setOpen((o) => !o) }}>
            <IconDeviceFloppy size={16} stroke={1.8} />
          </ActionIcon>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown p="xs" style={{ width: 220 }}>
        <TextInput
          {...INPUT}
          placeholder="Scene name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') save() }}
          data-ctl="scene-name"
          data-autofocus
        />
        <Checkbox
          size="xs"
          mt={6}
          label="Keep current camera"
          checked={withCamera}
          onChange={(e) => setWithCamera(e.currentTarget.checked)}
          data-ctl="scene-with-camera"
        />
        {exists && (
          <Text size="xs" c="orange" mt={6} data-ctl="scene-exists">
            “{trimmed}” exists and will be replaced.
          </Text>
        )}
        <Button size="xs" fullWidth mt={8} disabled={!trimmed} onClick={save}
          color={exists ? 'orange' : undefined} data-ctl="scene-save-ok">
          {exists ? 'Replace' : 'Save'}
        </Button>
      </Popover.Dropdown>
    </Popover>
  )
}

function SceneRow({ scene, names, menuOpen, onLoad, onRename, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(scene.name)
  const [confirm, setConfirm] = useState(false)
  const slug = scene.name

  if (editing) {
    const next = draft.trim()
    const ok = next && (next === scene.name || !names.includes(next))
    const finish = (commit) => {
      if (commit && ok && next !== scene.name) onRename(scene.name, next)
      setEditing(false)
    }
    return (
      <TextInput
        {...INPUT}
        autoFocus
        value={draft}
        error={ok ? null : true}
        onChange={(e) => setDraft(e.currentTarget.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') finish(true)
          if (e.key === 'Escape') finish(false)
        }}
        onBlur={() => finish(true)}
        data-ctl="scene-rename-input"
      />
    )
  }

  return (
    <div className="scenerow" data-scene={slug}>
      <button type="button" className="scenebtn" onClick={() => onLoad(scene.name)}
        data-ctl="scene-load" title={scene.camera ? `${scene.name} (with camera)` : scene.name}>
        {scene.name}
      </button>
      <Menu position="bottom-end" withinPortal onOpen={() => { menuOpen.current = true }}
        onClose={() => { menuOpen.current = false; setConfirm(false) }}>
        <Menu.Target>
          <ActionIcon variant="subtle" size="xs" color="gray" data-ctl="scene-menu"
            aria-label={`More for ${scene.name}`}>
            <IconDots size={14} />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item leftSection={<IconPencil size={14} />} data-ctl="scene-rename"
            onClick={() => { setDraft(scene.name); setEditing(true) }}>
            Rename
          </Menu.Item>
          <Menu.Item
            color="red"
            leftSection={<IconTrash size={14} />}
            closeMenuOnClick={confirm}
            onClick={() => (confirm ? onDelete(scene.name) : setConfirm(true))}
            data-ctl="scene-delete"
          >
            {confirm ? 'Click again to delete' : 'Delete'}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
    </div>
  )
}
