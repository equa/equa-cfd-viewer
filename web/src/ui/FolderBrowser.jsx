import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Group, Modal, ScrollArea, Table, Text,
} from '@mantine/core'
import { IconArrowUp, IconFolder, IconFolderPlus } from '@tabler/icons-react'
import { api } from '../api.js'

/*
 * Local mode's "Add folder": the server lists its own drives and folders, the
 * user walks down to one and adds it as a root. A folder that is a case, or
 * holds cases one level down, is marked so the user can tell where to stop.
 */
export function FolderBrowser({ opened, onClose, onAdded }) {
  const [path, setPath] = useState('')
  const [listing, setListing] = useState(null)
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    if (!opened) return undefined
    let cancelled = false
    setError(null)
    api.folders(path)
      .then((l) => { if (!cancelled) setListing(l) })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [opened, path])

  const add = () => {
    setAdding(true)
    api.addFolder(listing.path)
      .then(() => { onAdded(); onClose() })
      .catch((e) => setError(e.message))
      .finally(() => setAdding(false))
  }

  const up = () => setPath(listing?.parent ?? '')

  return (
    <Modal opened={opened} onClose={onClose} title="Add a folder with cases" size="lg"
      data-ctl="folder-browser">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Text size="xs" c="dimmed" truncate="start" data-ctl="folder-path">
          {/* truncate="start" is right-to-left; keep the path itself left-to-right */}
          <span dir="ltr">{listing?.path || 'Drives'}</span>
        </Text>
        <Button size="xs" variant="subtle" leftSection={<IconArrowUp size={14} />}
          onClick={up} disabled={!listing?.path} data-ctl="folder-up">
          Up
        </Button>
      </Group>
      {error && <Alert color="orange" variant="light" mb="xs">{error}</Alert>}
      <ScrollArea h={360} type="auto">
        <Table highlightOnHover verticalSpacing={4} fz="sm">
          <Table.Tbody>
            {(listing?.entries || []).map((e) => (
              <Table.Tr key={e.path} className="start-row" onClick={() => setPath(e.path)}
                data-ctl="folder-row">
                <Table.Td w={24}><IconFolder size={16} stroke={1.6} /></Table.Td>
                <Table.Td>{e.name}</Table.Td>
                <Table.Td ta="right">
                  {e.isCase && <Badge size="xs" variant="light">case</Badge>}
                  {e.hasCases && <Badge size="xs" variant="light" color="teal">has cases</Badge>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {listing && !listing.entries.length && (
          <Text size="sm" c="dimmed" mt="sm">No folders here.</Text>
        )}
      </ScrollArea>
      <Group justify="flex-end" mt="sm">
        <Button size="xs" variant="default" onClick={onClose}>Cancel</Button>
        <Button size="xs" leftSection={<IconFolderPlus size={14} />} onClick={add}
          loading={adding} disabled={!listing?.path} data-ctl="folder-add">
          Add this folder
        </Button>
      </Group>
    </Modal>
  )
}
