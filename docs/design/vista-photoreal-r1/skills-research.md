# 3D modeling skill review — 2026-09-06

The user requested public skills for better modeling, interior design, engineering
drawings and game physics while the first kitchen was being built. These are
community workflows with different dependencies; their names do not establish
quality on GPT-6-Astra or compatibility with this project's runtime.

| Source | Useful part for VISTA | Current decision |
| --- | --- | --- |
| [arjun988/blender-skills: archviz](https://github.com/arjun988/blender-skills/tree/8f778d2405a214b508d4c7d80742be8e43acdd52/.claude/skills/archviz) | Metric architecture, separated glazing, 24–35 mm interior cameras, eye height, soft daylight and practical lighting | Read the skill and both references; apply to the kitchen review. Existing Blender Python remains the execution method. |
| [arjun988/blender-skills: collision-proxy](https://github.com/arjun988/blender-skills/tree/8f778d2405a214b508d4c7d80742be8e43acdd52/.claude/skills/collision-proxy) | Dedicated simple colliders and convex assemblies | Reviewed. Needed when the props become simulated or graspable; visual meshes alone are insufficient. |
| [quodsoler/unreal-engine-skills: ue-physics-collision](https://github.com/quodsoler/unreal-engine-skills/tree/231c8571be6f3335685edc566a28ec6f9621361d/skills/ue-physics-collision) | Collision profiles, traces, constraints, mass and physical materials | Reviewed as reference; verify used APIs against local UE 5.7.3 source. Current fridge doors use driven transforms, not a Chaos hinge simulation. |
| [ifBars/blender-agent-studio](https://github.com/ifBars/blender-agent-studio/tree/b1cefdd1bcc1b7bf40423259a5c6fa154e2259f4) | Authored/exported asset comparison, multiview inspection and mechanical animation review | Read its asset-validation workflow. Its stated validated runtime is Blender 5.2; this project uses 4.5.8. Do not assume its scripts are validated here. |
| [Bonsai / IfcOpenShell skill package](https://github.com/Impertio-Studio/Blender-Bonsai-ifcOpenshell-Sverchok-Claude-Skill-Package/tree/dc56112d81b25b64d3e1c7b765673a035981543f) | Typed walls/slabs/openings, spatial containment, material layers and drawing workflows | Reviewed modeling workflow and identified drawing skill. Candidate for a future authoritative BIM source, once real measurements exist. |
| [jmwright/cadquery-llm-skill](https://github.com/jmwright/cadquery-llm-skill) | BRep parts, workplanes, selectors, engineering features and STEP output | Candidate for exact product parts and fittings; not required to render the current kitchen. |
| [GitHub freecad-scripts](https://github.com/github/awesome-copilot/tree/main/skills/freecad-scripts) | Constrained sketches, dimensional CAD and export | Candidate for editable engineering drawings and dimension-controlled assemblies. |

## Workflow decisions

- Use real dimensions as the source of truth. Generated reference images guide
  appearance and do not establish surveyed measurements or construction accuracy.
- Model architecture and manufactured parts with explicit dimensions, thickness,
  clearances and pivots; inspect glass, frame and furniture layers independently.
- Judge the actual exported asset inside UE as well as Blender renders. Import
  receipts check scale and axes, but screenshots and movement checks establish
  what the user can inspect through Sunshine.
- Keep visual geometry separate from simulated collision. Before adding grasping,
  dropping or force-driven doors, author convex collision, physical properties and
  contact/constraint tests. Do not advertise the current review as a full physics
  simulator.
- The downloaded skill documents are pinned review inputs outside Git. No external
  MCP server, model API, global plugin bundle or CAD application was installed by
  this research step.

Local source snapshots are in the run's `skill-research/` directory. Only the
archviz workflow was adopted for the current turn; other candidates are reviewed
references or future options, not claims of completed integrations.
