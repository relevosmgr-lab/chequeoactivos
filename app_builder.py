import pandas as pd
import json
import os
import subprocess

def procesar_datos():
    print("1. Leyendo archivos CSV...")
    df_ftth = pd.read_csv('Edificios_FTTH.csv', sep=';', low_memory=False, encoding='latin1')
    df_amba = pd.read_csv('Edificios_AMBA.csv', sep=';', low_memory=False, encoding='latin1')

    print("2. Filtrando y limpiando datos...")
    
    # Limpieza preliminar de espacios en la calle para poder filtrar bien
    df_ftth['CALLE'] = df_ftth['CALLE'].astype(str).str.strip()
    
    # Filtros: Subregión CABA, estado OPERATIVO y que CALLE no esté vacía ni sea 'nan'
    df_ftth = df_ftth[
        (df_ftth['SUBREGION_OORR'].isin(['CAPITAL NORTE', 'CAPITAL SUR'])) &
        (df_ftth['ESTADO'] == 'OPERATIVO') &
        (df_ftth['CALLE'] != '') &
        (df_ftth['CALLE'].str.lower() != 'nan')
    ].copy()

    # Limpiar NAP, PD y PC
    df_ftth['NAP'] = df_ftth['NAP'].fillna('Sin dato NAP')
    df_ftth['PD'] = df_ftth['NAP'].apply(lambda x: str(x)[:4] if len(str(x)) >= 4 and x != 'Sin dato NAP' else 'Sin dato PD')
    df_ftth['PC'] = df_ftth['NAP'].apply(lambda x: str(x)[:5] if len(str(x)) >= 5 and x != 'Sin dato NAP' else 'Sin dato PC')

    # Función estricta para alturas (permitimos que queden sin altura, pero las normalizamos)
    def clean_altura(val):
        if pd.isna(val) or str(val).strip() == "":
            return "No se encontro altura"
        val_str = str(val).strip()
        # Si es texto (ej: "Altura no valida...")
        if not val_str.replace('.', '', 1).isdigit():
            return "No se encontro altura"
        # Si es un numero con decimal (ej: "80.0")
        return str(int(float(val_str)))

    df_ftth['ALTURA'] = df_ftth['ALTURA'].apply(clean_altura)

    print("3. Cruzando direcciones secundarias...")
    df_amba_sec = df_amba[df_amba['DIRECCION'] == 'SECUNDARIA'].copy()
    df_amba_sec['ALTURA'] = df_amba_sec['ALTURA'].apply(clean_altura)
    
    secundarias_agrupadas = df_amba_sec.groupby('EDIFICIO').apply(
        lambda x: x[['CALLE', 'ALTURA']].to_dict('records'), include_groups=False
    ).reset_index(name='DIRECCIONES_SECUNDARIAS')

    df_final = pd.merge(df_ftth, secundarias_agrupadas, left_on='ACTIVO', right_on='EDIFICIO', how='left')
    df_final['DIRECCIONES_SECUNDARIAS'] = df_final['DIRECCIONES_SECUNDARIAS'].apply(lambda x: x if isinstance(x, list) else [])

    # Seleccionar columnas y guardar
    columnas = ['ACTIVO', 'SUBREGION_OORR', 'PD', 'PC', 'NAP', 'CALLE', 'ALTURA', 'ESTADO_CONSTRUCTIVO_EDIFICIO', 'DIRECCIONES_SECUNDARIAS', 'CIUDAD', 'PARTIDO']
    df_app = df_final[columnas].copy()
    
    df_app.to_json('Maestro_Edificios_CABA_App.json', orient='records', force_ascii=False)
    print(f" -> JSON generado con {len(df_app)} activos operativos y con calle definida.")

def generar_html():
    print("4. Generando index.html con formularios dinámicos...")
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relevamiento FTTH - CABA AF</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = { theme: { extend: { colors: { personal: { navy: '#001A70', cyan: '#00A1E4', hover: '#008bc2' } } } } }
    </script>
    
    <script type="module">
        import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
        import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-auth.js";
        import { getFirestore, doc, getDoc, setDoc, deleteDoc, getDocs, collection } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

        // ⚠️ PEGAR AQUÍ TU CONFIGURACIÓN DE FIREBASE ⚠️
        const firebaseConfig = {
        apiKey: "AIzaSyC1yyZ2N3t8nbtgECkshjl4MBgnjOtJj7M",
        authDomain: "relevos-9645a.firebaseapp.com",
        projectId: "relevos-9645a",
        storageBucket: "relevos-9645a.firebasestorage.app",
        messagingSenderId: "816456413666",
        appId: "1:816456413666:web:b0202740d9cb40a6f309bb",
        measurementId: "G-XXC9KMQZB2"
        };

        const app = initializeApp(firebaseConfig);
        const auth = getAuth(app);
        const db = getFirestore(app);
        const provider = new GoogleAuthProvider();
        const GAS_URL = "https://script.google.com/macros/s/AKfycbw6x0HZIsnlqKOpiKS2813hRKWRBMGELrjDrL99EqCn-Ayq_AIz4SdvLMcTVFbw_2vr6w/exec";

        let maestroDatos = [];
        let mapaRelevos = {}; 
        let usuarioActual = null;
        let rolUsuario = "nuevo";

        // Variables de Paginación y Fotos
        let resultadosActuales = [];
        let paginaActual = 1;
        const itemsPorPagina = 50;
        window.fotosActivos = {}; 

        onAuthStateChanged(auth, async (user) => {
            if (user) {
                usuarioActual = user;
                document.getElementById('login-screen').classList.add('hidden');
                const userRef = doc(db, "usuarios", user.email);
                const userSnap = await getDoc(userRef);
                if (userSnap.exists()) {
                    rolUsuario = userSnap.data().rol;
                    if (["autorizado", "supervisor", "superadmin"].includes(rolUsuario)) {
                        document.getElementById('app-screen').classList.remove('hidden');
                        document.getElementById('warning-screen').classList.add('hidden');
                        document.getElementById('user-email').innerText = `${user.email} (${rolUsuario.toUpperCase()})`;
                        if (rolUsuario === "supervisor" || rolUsuario === "superadmin") {
                            document.getElementById('panel-auditoria').classList.remove('hidden');
                        }
                        cargarDatosJSON(); 
                    } else { document.getElementById('warning-screen').classList.remove('hidden'); }
                } else {
                    await setDoc(userRef, { rol: "nuevo", email: user.email });
                    document.getElementById('warning-screen').classList.remove('hidden');
                }
            } else {
                document.getElementById('login-screen').classList.remove('hidden');
                document.getElementById('app-screen').classList.add('hidden');
                document.getElementById('warning-screen').classList.add('hidden');
            }
        });

        document.getElementById('btn-login').addEventListener('click', () => signInWithPopup(auth, provider));
        document.getElementById('btn-logout').addEventListener('click', () => signOut(auth));

        async function cargarDatosJSON() {
            try {
                const response = await fetch('./Maestro_Edificios_CABA_App.json?t=' + new Date().getTime());
                maestroDatos = await response.json();
                document.getElementById('status-db').innerText = `Base lista (${maestroDatos.length} activos)`;
            } catch (error) { document.getElementById('status-db').innerHTML = '<span class="text-red-500">Error en carga</span>'; }
        }

        async function actualizarMapaRelevos() {
            const querySnapshot = await getDocs(collection(db, "relevamientos"));
            mapaRelevos = {};
            querySnapshot.forEach((doc) => { mapaRelevos[doc.id] = doc.data(); });
        }

        window.aplicarFiltros = async () => {
            const btnBuscar = document.getElementById('btn-buscar');
            btnBuscar.innerText = "Sincronizando y buscando...";
            await actualizarMapaRelevos();

            const subregion = document.getElementById('filt-subregion').value;
            const pd = document.getElementById('filt-pd').value.trim().toUpperCase();
            const estConst = document.getElementById('filt-estado-const').value.toUpperCase();
            const estRelevo = document.getElementById('filt-estado-relevo').value;
            const calle = document.getElementById('filt-calle').value.trim().toUpperCase();
            const altura = document.getElementById('filt-altura').value.trim();
            const auditor = document.getElementById('filt-auditor').value.trim().toLowerCase();

            if (!subregion && !pd && !calle && !altura && !estConst && !estRelevo && !auditor) {
                alert("Por favor, ingrese al menos un filtro para buscar.");
                btnBuscar.innerText = "BUSCAR DIRECCIONES";
                return;
            }

            let resultados = maestroDatos.filter(edif => {
                if (subregion && edif.SUBREGION_OORR !== subregion) return false;
                if (pd && edif.PD !== pd) return false;
                if (estConst && (edif.ESTADO_CONSTRUCTIVO_EDIFICIO || "").toUpperCase() !== estConst) return false;

                const datosRelevo = mapaRelevos[edif.ACTIVO];
                const estaRelevado = !!datosRelevo;
                if (estRelevo === "RELEVADO" && !estaRelevado) return false;
                if (estRelevo === "PENDIENTE" && estaRelevado) return false;
                
                if (auditor) {
                    if (!estaRelevado) return false;
                    if (!(datosRelevo.tecnico || "").toLowerCase().includes(auditor)) return false;
                }

                if (calle || altura) {
                    const esLaPuertaCorrecta = (dirCalle, dirAltura) => {
                        const strCalle = String(dirCalle || "").toUpperCase();
                        const strAltura = String(dirAltura || "");
                        let pasaCalle = true; if (calle && !strCalle.includes(calle)) pasaCalle = false;
                        let pasaAltura = true; if (altura && !strAltura.startsWith(altura)) pasaAltura = false;
                        return pasaCalle && pasaAltura;
                    };
                    const matchPrincipal = esLaPuertaCorrecta(edif.CALLE, edif.ALTURA);
                    const matchSecundaria = edif.DIRECCIONES_SECUNDARIAS.some(sec => esLaPuertaCorrecta(sec.CALLE, sec.ALTURA));
                    if (!matchPrincipal && !matchSecundaria) return false;
                }
                return true;
            });

            resultados.sort((a, b) => {
                const calleA = (a.CALLE || "").toUpperCase();
                const calleB = (b.CALLE || "").toUpperCase();
                if (calleA < calleB) return -1;
                if (calleA > calleB) return 1;
                const altA = parseInt(a.ALTURA) || 0;
                const altB = parseInt(b.ALTURA) || 0;
                return altA - altB;
            });

            const maxResultados = 500;
            if (resultados.length > maxResultados) {
                resultados = resultados.slice(0, maxResultados);
                document.getElementById('resultados-count').innerHTML = `<span class="text-amber-600 font-bold">Límite alcanzado:</span> Mostrando ${maxResultados} activos.`;
            } else {
                document.getElementById('resultados-count').innerText = `Resultados: ${resultados.length} activos en ruta.`;
            }

            resultadosActuales = resultados;
            paginaActual = 1;
            btnBuscar.innerText = "BUSCAR DIRECCIONES";
            renderPagina();
        };

        window.renderPagina = () => {
            const container = document.getElementById('cards-container');
            const pagControls = document.getElementById('pagination-controls');
            container.innerHTML = '';
            
            if (resultadosActuales.length === 0) {
                container.innerHTML = '<p class="text-center text-gray-500 mt-8 font-semibold">No se encontraron direcciones.</p>';
                pagControls.classList.add('hidden');
                return;
            }

            const totalPaginas = Math.ceil(resultadosActuales.length / itemsPorPagina);
            const indexInicio = (paginaActual - 1) * itemsPorPagina;
            const indexFin = indexInicio + itemsPorPagina;
            const datosPagina = resultadosActuales.slice(indexInicio, indexFin);

            for (const edif of datosPagina) {
                const datosRelevo = mapaRelevos[edif.ACTIVO];
                const estaRelevado = !!datosRelevo;
                const estado = (edif.ESTADO_CONSTRUCTIVO_EDIFICIO || "DESCONOCIDO").toUpperCase();
                if (!fotosActivos[edif.ACTIVO]) fotosActivos[edif.ACTIVO] = []; 

                const card = document.createElement('div');
                let cardStyle = estaRelevado ? "bg-green-50 border-green-500" : (estado === "CONSTRUIDO" ? "bg-blue-50 border-personal-cyan" : (estado.includes("CONSTRUIR") ? "bg-amber-50 border-amber-500" : "bg-white border-gray-400"));
                let badgeStyle = estaRelevado ? "bg-green-500 text-white" : (estado === "CONSTRUIDO" ? "bg-personal-cyan text-white" : (estado.includes("CONSTRUIR") ? "bg-amber-500 text-white" : "bg-gray-500 text-white"));

                card.className = `p-4 rounded-xl shadow-md mb-4 border-l-4 ${cardStyle}`;
                
                let htmlSecundarias = edif.DIRECCIONES_SECUNDARIAS.length > 0 ? `<div class="mt-2 ml-4 pl-3 border-l-2 border-gray-300"><span class="text-[10px] font-bold text-gray-500 uppercase tracking-wide">Secundarias:</span><ul class="text-xs text-gray-700 mt-1">${edif.DIRECCIONES_SECUNDARIAS.map(s => `<li>• ${s.CALLE} <b>${s.ALTURA}</b></li>`).join('')}</ul></div>` : '';

                if (estaRelevado) {
                    card.innerHTML = `<div class="flex justify-between items-center mb-1"><span class="text-xs font-bold text-gray-500">ID: ${edif.ACTIVO} | NAP: ${edif.NAP}</span><span class="text-[10px] font-bold px-2 py-1 rounded shadow-sm tracking-wide ${badgeStyle}">RELEVADO</span></div><h3 class="text-xl font-bold text-gray-800">${edif.CALLE} ${edif.ALTURA}</h3>${htmlSecundarias}<div class="my-3 p-3 bg-white rounded border border-green-200 shadow-sm"><p class="text-green-700 font-extrabold text-sm">✅ ${datosRelevo.accion}</p><p class="text-gray-600 text-xs mt-1">Por: <b>${datosRelevo.tecnico}</b><br>Fecha: ${datosRelevo.fecha}</p><p class="mt-2 text-xs font-medium text-gray-700 p-2 bg-gray-50 border rounded">📝 Obs: ${datosRelevo.observacion}</p></div><button onclick="deshacerRelevo('${edif.ACTIVO}')" class="w-full mt-2 text-sm text-red-600 font-bold py-2 border border-red-200 bg-white rounded-lg shadow-sm hover:bg-red-50">Deshacer / Editar</button>`;
                } else {
                    let opcionesSelect = `<option value="">Seleccione Acción...</option><option value="CORREGIR ALTURA">Corregir Altura</option><option value="UNIFICAR DIRECCIONES">Unificar Direcciones</option><option value="NO ESTA CONSTRUIDO">No está construido / Obra</option>`;
                    if (estado !== "CONSTRUIDO") opcionesSelect += `<option value="INFORMAR CONSTRUIDO">Informar Construido</option><option value="NO ES EDIFICIO">No es Edificio</option><option value="IMPOSIBLE CONSTRUIR">Imposible Construir</option><option value="COMPETENCIA">Competencia</option><option value="NO EXISTE ALTURA">No existe altura</option>`;

                    card.innerHTML = `
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-xs font-bold text-gray-500">ID: ${edif.ACTIVO} | NAP: ${edif.NAP}</span>
                            <span class="text-[10px] font-bold px-2 py-1 rounded shadow-sm tracking-wide ${badgeStyle}">${edif.ESTADO_CONSTRUCTIVO_EDIFICIO}</span>
                        </div>
                        <h3 class="text-xl font-bold text-personal-navy">${edif.CALLE} ${edif.ALTURA}</h3>
                        ${htmlSecundarias}
                        
                        <div class="mt-4 space-y-3 bg-white/50 p-3 rounded-lg border border-gray-100">
                            <select id="accion-${edif.ACTIVO}" onchange="manejarAccionesDinamicas('${edif.ACTIVO}')" class="w-full p-2.5 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-personal-cyan outline-none font-medium text-personal-navy">${opcionesSelect}</select>
                            
                            <div id="form-dinamico-${edif.ACTIVO}" class="hidden p-3 bg-blue-50 border border-blue-200 rounded-lg"></div>

                            <input type="text" id="obs-${edif.ACTIVO}" placeholder="Observación general (Obligatoria)" class="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-personal-cyan outline-none">
                            
                            <div class="bg-gray-50 border border-gray-200 p-3 rounded-lg">
                                <div class="flex justify-between items-center mb-2">
                                    <span class="text-xs font-bold text-gray-600">Fotos: <span id="count-${edif.ACTIVO}">0/15</span></span>
                                    <div class="flex gap-2">
                                        <button onclick="document.getElementById('cam-${edif.ACTIVO}').click()" class="bg-blue-100 text-blue-700 px-3 py-1.5 rounded-md text-xs font-bold border border-blue-200 flex items-center gap-1 hover:bg-blue-200"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"></path></svg></button>
                                        <button onclick="document.getElementById('gal-${edif.ACTIVO}').click()" class="bg-gray-200 text-gray-700 px-3 py-1.5 rounded-md text-xs font-bold border border-gray-300 flex items-center gap-1 hover:bg-gray-300"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg></button>
                                    </div>
                                    <input type="file" id="cam-${edif.ACTIVO}" accept="image/*" capture="environment" class="hidden" onchange="agregarFotos('${edif.ACTIVO}', this.files)">
                                    <input type="file" id="gal-${edif.ACTIVO}" accept="image/*" multiple class="hidden" onchange="agregarFotos('${edif.ACTIVO}', this.files)">
                                </div>
                                <div id="thumbs-${edif.ACTIVO}" class="flex flex-wrap gap-2 mt-2"></div>
                            </div>
                            
                            <button onclick="enviarRelevo('${edif.ACTIVO}')" class="w-full bg-personal-cyan text-white p-3 rounded-lg font-bold shadow-md hover:bg-personal-hover transition tracking-wide">ENVIAR RELEVAMIENTO</button>
                        </div>
                    `;
                }
                container.appendChild(card);
                if (!estaRelevado) dibujarMiniaturas(edif.ACTIVO);
            }

            document.getElementById('page-indicator').innerText = `Pág ${paginaActual} de ${totalPaginas}`;
            document.getElementById('btn-prev').disabled = (paginaActual === 1);
            document.getElementById('btn-next').disabled = (paginaActual === totalPaginas);
            pagControls.classList.remove('hidden');
            window.scrollTo(0, 0); 
        };

        window.cambiarPagina = (delta) => { paginaActual += delta; renderPagina(); };

        // --- MANEJO DE FORMULARIOS DINÁMICOS ---
        window.manejarAccionesDinamicas = (activo) => {
            const accion = document.getElementById(`accion-${activo}`).value;
            const container = document.getElementById(`form-dinamico-${activo}`);
            
            if (accion === "CORREGIR ALTURA") {
                container.innerHTML = `
                    <label class="block text-xs font-bold text-personal-navy mb-1">Altura correcta principal (*)</label>
                    <input type="number" id="alt-ppal-${activo}" placeholder="Ej: 3300" class="w-full p-2 border rounded mb-3 text-sm focus:ring-1 focus:ring-personal-cyan outline-none">
                    
                    <label class="flex items-center text-xs font-bold text-gray-700 mb-2 cursor-pointer">
                        <input type="checkbox" id="chk-otras-alt-${activo}" class="mr-2 w-4 h-4 text-personal-cyan rounded focus:ring-personal-cyan" onchange="toggleOtrasAlturas('${activo}')">
                        ¿Tiene otras alturas secundarias?
                    </label>
                    
                    <div id="otras-alturas-container-${activo}" class="hidden flex-col gap-2">
                        <div id="lista-otras-alt-${activo}" class="flex flex-col gap-2"></div>
                        <button type="button" onclick="sumarAlturaSecundaria('${activo}')" class="text-xs bg-white border-2 border-personal-cyan text-personal-cyan font-bold py-1.5 px-3 rounded-md hover:bg-blue-100 w-max shadow-sm transition">
                            + Sumar otra altura
                        </button>
                    </div>
                `;
                container.classList.remove('hidden');
            } else {
                // Acá a futuro podemos agregar los formularios de "Unificar Direcciones", etc.
                container.innerHTML = '';
                container.classList.add('hidden');
            }
        };

        window.toggleOtrasAlturas = (activo) => {
            const chk = document.getElementById(`chk-otras-alt-${activo}`).checked;
            const container = document.getElementById(`otras-alturas-container-${activo}`);
            if (chk) {
                container.classList.remove('hidden'); container.classList.add('flex');
                if (document.getElementById(`lista-otras-alt-${activo}`).children.length === 0) sumarAlturaSecundaria(activo);
            } else {
                container.classList.add('hidden'); container.classList.remove('flex');
            }
        };

        window.sumarAlturaSecundaria = (activo) => {
            const idRow = Date.now();
            const lista = document.getElementById(`lista-otras-alt-${activo}`);
            const div = document.createElement('div');
            div.className = "flex items-center gap-2";
            div.id = `row-alt-${idRow}`;
            div.innerHTML = `
                <input type="number" class="w-full p-2 border rounded text-sm input-extra-alt-${activo}" placeholder="Ej: 3302">
                <button type="button" onclick="document.getElementById('row-alt-${idRow}').remove()" class="bg-red-500 text-white rounded p-2 shadow-sm font-bold text-xs hover:bg-red-600">X</button>
            `;
            lista.appendChild(div);
        };

        // --- FOTOS ---
        window.agregarFotos = async (activo, files) => {
            if (!files || files.length === 0) return;
            let currentFotos = window.fotosActivos[activo] || [];
            for (let i = 0; i < files.length; i++) {
                if (currentFotos.length >= 15) { alert("Límite de 15 fotos alcanzado."); break; }
                const base64 = await comprimirImagen(files[i]);
                currentFotos.push(base64);
            }
            window.fotosActivos[activo] = currentFotos;
            dibujarMiniaturas(activo);
        };
        window.eliminarFoto = (activo, index) => { window.fotosActivos[activo].splice(index, 1); dibujarMiniaturas(activo); };
        window.dibujarMiniaturas = (activo) => {
            const fotos = window.fotosActivos[activo] || [];
            const container = document.getElementById(`thumbs-${activo}`);
            if(!container) return; 
            container.innerHTML = '';
            fotos.forEach((b64, index) => {
                container.innerHTML += `<div class="relative w-12 h-12 shadow-sm rounded border border-gray-300"><img src="${b64}" class="object-cover w-full h-full rounded"><button onclick="eliminarFoto('${activo}', ${index})" class="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full w-5 h-5 text-[10px] flex items-center justify-center font-extrabold shadow-md">X</button></div>`;
            });
            document.getElementById(`count-${activo}`).innerText = `${fotos.length}/15`;
        };

        // --- ENVÍO DE DATOS ---
        window.enviarRelevo = async (activo) => {
            const accion = document.getElementById(`accion-${activo}`).value;
            let obsGeneral = document.getElementById(`obs-${activo}`).value.trim();
            const fotosB64 = window.fotosActivos[activo] || [];
            
            if (!accion) { alert("Debe seleccionar una acción."); return; }

            // Lógica de captura para CORREGIR ALTURA
            if (accion === "CORREGIR ALTURA") {
                const altPpal = document.getElementById(`alt-ppal-${activo}`).value.trim();
                if (!altPpal) { alert("Debe ingresar la altura correcta principal."); return; }
                
                let extrasStr = "";
                const chkOtras = document.getElementById(`chk-otras-alt-${activo}`);
                if (chkOtras && chkOtras.checked) {
                    const extraInputs = document.querySelectorAll(`.input-extra-alt-${activo}`);
                    let arrExtras = [];
                    extraInputs.forEach(input => { if(input.value.trim()) arrExtras.push(input.value.trim()); });
                    if (arrExtras.length > 0) extrasStr = ` | Secundarias: ${arrExtras.join(', ')}`;
                }
                
                // Anexamos la información estructurada al principio de la observación
                obsGeneral = `[Nueva Altura Principal: ${altPpal}${extrasStr}] ${obsGeneral ? '- Obs: ' + obsGeneral : ''}`;
            } else if (!obsGeneral) {
                alert("La observación es obligatoria."); return;
            }

            const btn = event.target;
            btn.innerText = "Subiendo fotos y datos..."; btn.classList.add('opacity-75', 'cursor-not-allowed'); btn.disabled = true;

            try {
                const payload = {
                    fecha: new Date().toLocaleString("es-AR"), tecnico: usuarioActual.email,
                    activo: activo, accion: accion, observacion: obsGeneral, fotos: fotosB64
                };

                const response = await fetch(GAS_URL, { method: 'POST', body: JSON.stringify(payload) });
                const result = await response.json();
                
                if(result.status === "success") {
                    await setDoc(doc(db, "relevamientos", activo), { fecha: payload.fecha, tecnico: payload.tecnico, accion: payload.accion, observacion: payload.observacion });
                    window.fotosActivos[activo] = []; 
                    aplicarFiltros(); 
                } else {
                    alert("Error en servidor: " + result.message);
                    btn.innerText = "ENVIAR RELEVAMIENTO"; btn.disabled = false; btn.classList.remove('opacity-75');
                }
            } catch (error) {
                alert("Error de conexión.");
                btn.innerText = "ENVIAR RELEVAMIENTO"; btn.disabled = false; btn.classList.remove('opacity-75');
            }
        };

        window.deshacerRelevo = async (activo) => {
            if(confirm("¿Deseas editar este relevamiento?")) {
                await deleteDoc(doc(db, "relevamientos", activo));
                aplicarFiltros();
            }
        };

        function comprimirImagen(file) {
            return new Promise((resolve) => {
                const reader = new FileReader(); reader.readAsDataURL(file);
                reader.onload = (e) => {
                    const img = new Image(); img.src = e.target.result;
                    img.onload = () => {
                        const canvas = document.createElement('canvas'); const scaleSize = 800 / img.width;
                        canvas.width = 800; canvas.height = img.height * scaleSize;
                        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                        resolve(canvas.toDataURL('image/jpeg', 0.7)); 
                    };
                };
            });
        }
    </script>
</head>
<body class="bg-gray-100 min-h-screen font-sans">
    <div id="login-screen" class="flex flex-col items-center justify-center min-h-screen bg-personal-navy">
        <div class="bg-white p-10 rounded-2xl shadow-2xl text-center max-w-sm w-full mx-4">
            <h1 class="text-3xl font-extrabold text-personal-navy tracking-tight mb-2">Despliegue AF</h1>
            <p class="mb-8 text-gray-500 text-sm">Sistema de Relevamiento</p>
            <button id="btn-login" class="w-full bg-personal-cyan text-white py-3 rounded-lg font-bold hover:bg-personal-hover">Ingresar con Google</button>
        </div>
    </div>

    <div id="warning-screen" class="hidden flex items-center justify-center min-h-screen bg-gray-100">
        <div class="bg-white p-8 rounded-xl shadow border-t-4 border-yellow-400 text-center mx-4"><h2 class="text-xl font-bold mb-2">Acceso Pendiente</h2><p class="text-sm">Requiere autorización.</p></div>
    </div>

    <div id="app-screen" class="hidden max-w-md mx-auto bg-gray-100 min-h-screen flex flex-col">
        <div class="bg-personal-navy text-white px-4 py-3 sticky top-0 z-20 flex justify-between items-center border-b-4 border-personal-cyan shadow-md">
            <div><h1 class="font-bold tracking-wide">Telecom <span class="text-personal-cyan">Relevo</span></h1><p id="user-email" class="text-[10px] text-gray-300"></p></div>
            <button id="btn-logout" class="text-xs bg-white/10 px-3 py-1.5 rounded">Salir</button>
        </div>

        <div class="bg-white shadow-sm z-10 p-4 border-b">
            <div class="flex justify-between items-center mb-3">
                <h2 class="font-bold text-personal-navy text-sm">Buscador Operativo</h2><span id="status-db" class="text-[10px] text-gray-400">Cargando...</span>
            </div>
            
            <div class="grid grid-cols-2 gap-3 mb-3">
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">Subregión</label><select id="filt-subregion" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm"><option value="">Todas</option><option value="CAPITAL NORTE">Capital Norte</option><option value="CAPITAL SUR">Capital Sur</option></select></div>
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">PD</label><input type="text" id="filt-pd" placeholder="Ej: VCRG" maxlength="4" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase"></div>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-3">
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">Estado Const.</label><select id="filt-estado-const" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm"><option value="">Todos</option><option value="CONSTRUIDO">Construido</option><option value="A CONSTRUIR">A Construir</option><option value="SIN ESTADO">Sin Estado</option></select></div>
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">Estado Relevo</label><select id="filt-estado-relevo" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm font-bold text-personal-navy"><option value="">Todos</option><option value="PENDIENTE" selected>Falta Relevar</option><option value="RELEVADO">Relevado</option></select></div>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-3">
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">Calle</label><input type="text" id="filt-calle" placeholder="Nombre" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase"></div>
                <div><label class="block text-[10px] font-bold text-gray-500 uppercase">Altura</label><input type="number" id="filt-altura" placeholder="Ej: 33" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm"></div>
            </div>

            <div id="panel-auditoria" class="hidden mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <label class="block text-[10px] font-bold text-amber-800 uppercase mb-1">🔍 Panel Supervisor: Relevado por</label><input type="text" id="filt-auditor" placeholder="Ej: jlopez@teco.com.ar" class="w-full p-2 border border-amber-300 rounded bg-white text-sm">
            </div>

            <button id="btn-buscar" onclick="aplicarFiltros()" class="w-full bg-personal-navy text-white font-bold py-2.5 rounded shadow flex justify-center items-center hover:bg-blue-900 transition">BUSCAR DIRECCIONES</button>
        </div>

        <div class="bg-gray-100 flex-1 p-4 pb-20">
            <p id="resultados-count" class="text-xs text-gray-500 font-bold mb-3 text-center tracking-wide">Use los filtros para buscar</p>
            <div id="cards-container"></div>
            
            <div id="pagination-controls" class="hidden mt-6 flex justify-between items-center bg-white p-2 rounded shadow-sm border border-gray-200">
                <button id="btn-prev" onclick="cambiarPagina(-1)" class="px-4 py-2 bg-gray-200 text-gray-700 rounded text-sm font-bold disabled:opacity-30 disabled:cursor-not-allowed">Anterior</button>
                <span id="page-indicator" class="text-xs font-bold text-personal-navy">Pág 1/10</span>
                <button id="btn-next" onclick="cambiarPagina(1)" class="px-4 py-2 bg-personal-cyan text-white rounded text-sm font-bold disabled:opacity-30 disabled:cursor-not-allowed hover:bg-personal-hover">Siguiente</button>
            </div>
        </div>
    </div>
</body>
</html>"""
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(" -> index.html generado con éxito.")

def subir_a_github():
    print("5. Subiendo actualizaciones a GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Actualización automática de base de datos y app"], check=True)
        subprocess.run(["git", "push"], check=True)
        print(" -> ¡Despliegue en GitHub completado con éxito! Tu web está actualizada.")
    except Exception as e:
        print("⚠️ Hubo un error al intentar subir a Git. ¿Está inicializado el repositorio?")
        print("Error técnico:", e)

if __name__ == "__main__":
    print("=== INICIANDO CONSTRUCCIÓN DE LA APP ===")
    procesar_datos()
    generar_html()
    subir_a_github()
    print("=== PROCESO FINALIZADO ===")