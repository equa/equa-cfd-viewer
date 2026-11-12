import { useState } from 'react'
import { ActionIcon, Collapse, Group, Text, Tooltip } from '@mantine/core'
import {
  IconArrowUpRight, IconBlur, IconBulb, IconChevronDown, IconChevronRight, IconCube, IconEye,
  IconEyeOff, IconHome, IconSquare, IconVector,
} from '@tabler/icons-react'
import { TOOLS, TOOL_PART } from '../scene/state.js'
import { LabelledSlider, SectionTitle } from './controls.jsx'
import {
  BoundaryTool, ContourTool, CutPlaneTool, GeometryTool, GlyphTool, StreamTool,
} from './tools.jsx'

/*
 * The side pane, in three titled sections: the objects (a row's button picks
 * which settings show, its eye toggles what is drawn -- you routinely want a
 * slice and streamlines both visible while tuning one), the picked object's
 * settings, and Lighting, folded by default.
 *
 * The settings panels stay mounted and merely hidden, so a tool switch does not
 * throw away a half-typed value or a draft that has not been applied yet.
 */

// Tool key -> icon, kept beside BUILDERS so adding a tool is one place.
const ICONS = {
  square: IconSquare,
  cube: IconCube,
  blur: IconBlur,
  stream: IconVector,
  arrow: IconArrowUpRight,
  home: IconHome,
}

const BUILDERS = {
  cutplane: CutPlaneTool,
  boundary: BoundaryTool,
  contour: ContourTool,
  stream: StreamTool,
  glyph: GlyphTool,
  geometry: GeometryTool,
}

export function SidePane({
  meta, request, setRequest, appearance, setAppearance, setStyle, plane,
  comets, setComets, canAnimate, tubes, setTubes, domain,
}) {
  const [lightingOpen, setLightingOpen] = useState(false)
  const active = appearance.activeTool || 'cutplane'
  const setVisible = (part, on) => setAppearance({
    visible: { ...appearance.visible, [part]: on },
  })

  return (
    <div className="sidepane">
      <section className="section">
        <SectionTitle>Objects</SectionTitle>
      <div className="toolstack">
        {TOOLS.map(({ key, title, icon }) => {
          const part = TOOL_PART[key]
          const on = appearance.visible[part] !== false
          const disabled = key === 'geometry' && meta && !meta.hasGeometry
          const Icon = ICONS[icon]
          const Eye = on ? IconEye : IconEyeOff
          return (
            <div key={key} className={`toolrow${active === key ? ' active' : ''}`}>
              <button
                type="button"
                className="toolbtn"
                onClick={() => setAppearance({ activeTool: key })}
                data-ctl={`tool-${key}`}
              >
                <Icon size={16} stroke={1.6} className="toolicon" />
                {title}
              </button>
              <Tooltip label={on ? 'Hide' : 'Show'} openDelay={600}>
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  color={on ? 'blue' : 'gray'}
                  disabled={disabled}
                  onClick={() => setVisible(part, !on)}
                  data-ctl={`show-${key}`}
                  aria-label={`${on ? 'Hide' : 'Show'} ${title}`}
                >
                  <Eye size={16} stroke={1.6} />
                </ActionIcon>
              </Tooltip>
            </div>
          )
        })}
      </div>
      </section>

      {meta ? TOOLS.map(({ key, title, kind }) => {
        const Tool = BUILDERS[key]
        const part = TOOL_PART[key]
        return (
          <section key={key} hidden={active !== key} className="section toolpanel">
            <SectionTitle kind={kind}>{title}</SectionTitle>
            <Tool
              meta={meta}
              request={request}
              setRequest={setRequest}
              style={appearance.styles[part] || {}}
              setStyle={(patch) => setStyle(part, patch)}
              plane={plane}
              comets={comets}
              setComets={setComets}
              canAnimate={canAnimate}
              tubes={tubes}
              setTubes={setTubes}
              domain={domain}
            />
          </section>
        )
      }) : null}

      {/* Global fine-tuning; the sliders drive shader uniforms, so they are live. */}
      <section className="section">
        <SectionTitle
          right={(
            <ActionIcon variant="subtle" size="sm" color="gray"
              onClick={() => setLightingOpen((o) => !o)} data-ctl="lighting-toggle"
              aria-label={lightingOpen ? 'Fold Lighting' : 'Unfold Lighting'}>
              {lightingOpen ? <IconChevronDown size={15} /> : <IconChevronRight size={15} />}
            </ActionIcon>
          )}
        >
          Lighting
        </SectionTitle>
        <Collapse expanded={lightingOpen}>
            <Group justify="space-between" mb={6}>
              <Text size="xs" c="dimmed">Light kit</Text>
              <ActionIcon
                variant="subtle"
                size="sm"
                color={appearance.lighting.lightKit ? 'blue' : 'gray'}
                onClick={() => setAppearance({
                  lighting: { ...appearance.lighting, lightKit: !appearance.lighting.lightKit },
                })}
                data-ctl="light-kit"
                aria-label="Toggle the light kit"
              >
                <IconBulb size={15} stroke={1.6} />
              </ActionIcon>
            </Group>
            <LabelledSlider
              label="Ambient"
              min={0}
              max={1}
              step={0.05}
              live
              value={appearance.lighting.ambient}
              onChange={(v) => setAppearance({
                lighting: { ...appearance.lighting, ambient: v },
              })}
              data-ctl="light-ambient"
            />
            <LabelledSlider
              label="Diffuse"
              min={0}
              max={1}
              step={0.05}
              live
              value={appearance.lighting.diffuse}
              onChange={(v) => setAppearance({
                lighting: { ...appearance.lighting, diffuse: v },
              })}
              data-ctl="light-diffuse"
            />
        </Collapse>
      </section>
    </div>
  )
}

