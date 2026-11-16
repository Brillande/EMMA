import { Fold } from "./components/Fold";
import { AppUpdate } from "./components/AppUpdate";
import { ModelsPack } from "./components/ModelsPack";
import { tr } from "./lib/i18n";

/**
 * Licencia, titular y dónde está el código fuente.
 *
 * La AGPL-3.0 (§6) pide que quien recibe el programa en forma ejecutable pueda obtener su
 * código fuente, y (§13) que quien lo use por red pueda descargarlo. Hoy EMMA solo escucha en
 * loopback, pero un pie visible deja cubierto el caso de que alguien lo despliegue en red.
 * Texto de producto, no clínico: se puede redactar aquí. El pliegue lleva el signo de «acerca
 * de» (`about`, el círculo con la i) por la pieza común (`Fold`, §5.33.11).
 */
export function About() {
  return (
    <footer className="about">
      <Fold concept="about" label={tr("Acerca de EMMA", "About EMMA")}>
        <p className="secondary">
          {tr(
            "Software libre bajo la GNU Affero General Public License v3.0 o posterior, sin garantía. Incorpora código de Polaris (© 2026 la autora de Polaris, «Beyond the Protocol», AGPL-3.0-or-later). El texto de la licencia (LICENSE) y el inventario de código y datos de terceros (NOTICE) están en la carpeta de recursos de la instalación.",
            "Free software under the GNU Affero General Public License v3.0 or later, with no warranty. It includes code from Polaris (copyright 2026 the author of Polaris, “Beyond the Protocol”, AGPL-3.0-or-later). The license text (LICENSE) and the inventory of third-party code and data (NOTICE) are in the resources folder of the installation.",
          )}
        </p>
        <p className="secondary">
          {tr(
            "Código fuente: se entrega junto al proyecto; quien reciba este programa tiene derecho a obtenerlo. Apoyo a la decisión: no diagnostica, no prescribe y no sustituye el juicio clínico.",
            "Source code: it is delivered with the project; whoever receives this program has the right to obtain it. Decision support: it does not diagnose, does not prescribe and does not replace clinical judgment.",
          )}
        </p>
      </Fold>
      {/* El paquete de modelos: lo instalado y «Descargar modelos» (2026-11-15). */}
      <ModelsPack />
      {/* Actualizar EMMA a la versión publicada: comprobar, bajar e instalar, cada paso a mano (2026-11-16). */}
      <AppUpdate />
    </footer>
  );
}
