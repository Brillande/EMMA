import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { EMPTY_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { State, useLoad, useWrite } from "./PlannerPanels";
import { plannerApi } from "./plannerApi";

/**
 * Los miembros de la casa en el planificador (Marplanner): quién está, alta de uno nuevo y
 * archivar o recuperar.
 *
 * Por qué así: Marplanner no borra a nadie; archiva (su ADR-025), y archivar conserva lo que
 * esa persona hizo. Aquí igual. No se pide la fecha de nacimiento ni el color: la fecha es un dato
 * personal que el planificador de a bordo no necesita, y el color de miembro en EMMA no se usa (la
 * tabla F.5-1 reserva el color para significados). Las palabras del rol son las de Marplanner.
 */

const ROLE: Record<string, string> = { parent: "Padre", child: "Hijo" };

export function PlannerMembersPanel() {
  const members = useLoad(() => plannerApi.members(), "members-admin");
  const write = useWrite(members.reload);
  const [name, setName] = useState("");
  const [role, setRole] = useState<"parent" | "child">("child");
  const list = [...(members.data ?? [])].sort(
    (a, b) => Number(a.lifecycle !== "active") - Number(b.lifecycle !== "active"),
  );
  return (
    <section data-ui="planner-members" className="panel" aria-label="Miembros de la casa">
      <PanelTitle concept="identity">Miembros de la casa</PanelTitle>
      <State loaded={members} reading="Leyendo los miembros…" />
      {write.notice}
      {members.data !== null && list.length === 0 && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>No hay miembros.</MarkOf>
        </p>
      )}
      <ul className="planner-list">
        {list.map((member) => {
          const active = member.lifecycle === "active";
          return (
            <li key={member.id} className="planner-row">
              <span>
                {active ? (
                  member.displayName
                ) : (
                  /* Archivado: el gris de «no disponible», con su dibujo y su palabra. */
                  <MarkOf mark={UNAVAILABLE_MARK}>{member.displayName}</MarkOf>
                )}{" "}
                <span className="secondary">
                  · {ROLE[member.role] ?? member.role}
                  {!active && " · archivado"}
                </span>
              </span>
              <Command
                pictogram={active ? "slash-circle" : "check"}
                disabled={write.busy}
                onClick={() =>
                  void write.run(() =>
                    active ? plannerApi.archiveMember(member.id) : plannerApi.restoreMember(member.id),
                  )
                }
              >
                {active ? "Archivar" : "Recuperar"}
              </Command>
            </li>
          );
        })}
      </ul>
      <Fold data-ui="planner-members-add" concept="declare" label="Añadir un miembro">
        <div className="inline-form">
          <input
            value={name}
            maxLength={60}
            placeholder="nombre"
            aria-label="Nombre del miembro"
            onChange={(e) => setName(e.target.value)}
          />
          <select value={role} aria-label="Rol" onChange={(e) => setRole(e.target.value as "parent" | "child")}>
            <option value="parent">{ROLE.parent}</option>
            <option value="child">{ROLE.child}</option>
          </select>
          <Command
            concept="register"
            disabled={write.busy || name.trim() === ""}
            onClick={() =>
              void write.run(async () => {
                await plannerApi.createMember(name.trim(), role);
                setName("");
              })
            }
          >
            Añadir
          </Command>
        </div>
      </Fold>
    </section>
  );
}
