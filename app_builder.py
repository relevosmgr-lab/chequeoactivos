import pandas as pd
import json
import os
import subprocess

def procesar_datos():
    print("1. Leyendo archivos CSV...")
    # Agregamos encoding='latin1' a ambas líneas
    df_ftth = pd.read_csv('Edificios_FTTH.csv', sep=';', low_memory=False, encoding='latin1')
    df_amba = pd.read_csv('Edificios_AMBA.csv', sep=';', low_memory=False, encoding='latin1')

    print("2. Filtrando y limpiando datos...")
    # Filtrar subregiones
    df_ftth = df_ftth[df_ftth['SUBREGION_OORR'].isin(['CAPITAL NORTE', 'CAPITAL SUR'])].copy()

    # Limpiar NAP, PD y PC
    df_ftth['NAP'] = df_ftth['NAP'].fillna('Sin dato NAP')
    df_ftth['PD'] = df_ftth['NAP'].apply(lambda x: str(x)[:4] if len(str(x)) >= 4 and x != 'Sin dato NAP' else 'Sin dato PD')
    df_ftth['PC'] = df_ftth['NAP'].apply(lambda x: str(x)[:5] if len(str(x)) >= 5 and x != 'Sin dato NAP' else 'Sin dato PC')

    # Función estricta para alturas
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
        lambda x: x[['CALLE', 'ALTURA']].to_dict('records')
    ).reset_index(name='DIRECCIONES_SECUNDARIAS')

    df_final = pd.merge(df_ftth, secundarias_agrupadas, left_on='ACTIVO', right_on='EDIFICIO', how='left')
    df_final['DIRECCIONES_SECUNDARIAS'] = df_final['DIRECCIONES_SECUNDARIAS'].apply(lambda x: x if isinstance(x, list) else [])

    # Seleccionar columnas y guardar
    columnas = ['ACTIVO', 'SUBREGION_OORR', 'PD', 'PC', 'NAP', 'CALLE', 'ALTURA', 'ESTADO_CONSTRUCTIVO_EDIFICIO', 'DIRECCIONES_SECUNDARIAS', 'CIUDAD', 'PARTIDO']
    df_app = df_final[columnas].copy()
    
    df_app.to_json('Maestro_Edificios_CABA_App.json', orient='records', force_ascii=False)
    print(f" -> JSON generado con {len(df_app)} activos.")

def generar_html():
    print("4. Generando index.html...")
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relevamiento FTTH - CABA AF</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        personal: {
                            navy: '#001A70',
                            cyan: '#00A1E4',
                            hover: '#008bc2'
                        }
                    }
                }
            }
        }
    </script>
    
    <script type="module">
        import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-app.js";
        import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-auth.js";
        import { getFirestore, doc, getDoc, setDoc, deleteDoc } from "https://www.gstatic.com/firebasejs/10.8.1/firebase-firestore.js";

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
        let usuarioActual = null;

        onAuthStateChanged(auth, async (user) => {
            if (user) {
                usuarioActual = user;
                document.getElementById('login-screen').classList.add('hidden');
                
                const userRef = doc(db, "usuarios", user.email);
                const userSnap = await getDoc(userRef);
                
                if (userSnap.exists()) {
                    const rol = userSnap.data().rol;
                    if (rol === "autorizado" || rol === "superadmin") {
                        document.getElementById('app-screen').classList.remove('hidden');
                        document.getElementById('warning-screen').classList.add('hidden');
                        document.getElementById('user-email').innerText = user.email;
                        cargarDatosJSON(); 
                    } else {
                        document.getElementById('warning-screen').classList.remove('hidden');
                    }
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
            } catch (error) {
                console.error("Error:", error);
                document.getElementById('status-db').innerHTML = '<span class="text-red-500">Error en carga</span>';
            }
        }

        window.aplicarFiltros = () => {
            const subregion = document.getElementById('filt-subregion').value;
            const pd = document.getElementById('filt-pd').value.trim().toUpperCase();
            const pc = document.getElementById('filt-pc').value.trim().toUpperCase();
            const nap = document.getElementById('filt-nap').value.trim().toUpperCase();
            const calle = document.getElementById('filt-calle').value.trim().toUpperCase();
            const altura = document.getElementById('filt-altura').value.trim();

            if (!subregion && !pd && !pc && !nap && !calle && !altura) {
                alert("Por favor, ingrese al menos un filtro para buscar.");
                return;
            }

            const resultados = maestroDatos.filter(edif => {
                // Filtros exactos opcionales
                if (subregion && edif.SUBREGION_OORR !== subregion) return false;
                if (pd && edif.PD !== pd) return false;
                if (pc && edif.PC !== pc) return false;
                
                // Filtros de búsqueda parcial / progresiva
                if (nap && !edif.NAP.includes(nap)) return false;
                if (calle && !edif.CALLE.includes(calle)) return false;
                if (altura && !String(edif.ALTURA).startsWith(altura)) return false;
                
                return true;
            });

            const maxResultados = 150;
            if (resultados.length > maxResultados) {
                document.getElementById('resultados-count').innerHTML = `<span class="text-red-500 font-bold">¡Demasiados resultados (${resultados.length})!</span> Mostrando los primeros ${maxResultados} para cuidar la memoria. Refiná tu búsqueda.`;
                renderTarjetas(resultados.slice(0, maxResultados));
            } else {
                document.getElementById('resultados-count').innerText = `Resultados encontrados: ${resultados.length}`;
                renderTarjetas(resultados);
            }
        };

        async function renderTarjetas(datosFiltrados) {
            const container = document.getElementById('cards-container');
            container.innerHTML = '';
            
            if (datosFiltrados.length === 0) {
                container.innerHTML = '<p class="text-center text-gray-500 mt-8">No se encontraron direcciones.</p>';
                return;
            }

            for (const edif of datosFiltrados) {
                const relevoRef = doc(db, "relevamientos", edif.ACTIVO);
                const relevoSnap = await getDoc(relevoRef);
                const estaRelevado = relevoSnap.exists();
                const datosRelevo = estaRelevado ? relevoSnap.data() : null;

                const card = document.createElement('div');
                card.className = `p-4 border rounded-xl shadow-sm mb-4 ${estaRelevado ? 'bg-green-50 border-green-500' : 'bg-white border-gray-200'}`;
                
                // --- SANGRADO Y ESTILO DE DIRECCIONES SECUNDARIAS ---
                let htmlSecundarias = edif.DIRECCIONES_SECUNDARIAS.length > 0 
                    ? `<div class="mt-2 ml-4 pl-3 border-l-2 border-personal-cyan">
                        <span class="text-[10px] font-bold text-gray-500 uppercase tracking-wide">Direcciones Secundarias:</span>
                        <ul class="text-xs text-gray-700 mt-1 space-y-1">
                            ${edif.DIRECCIONES_SECUNDARIAS.map(s => `<li>• ${s.CALLE} <b>${s.ALTURA}</b></li>`).join('')}
                        </ul>
                       </div>` 
                    : '';

                if (estaRelevado) {
                    card.innerHTML = `
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-xs font-bold text-gray-400">ID: ${edif.ACTIVO} | NAP: ${edif.NAP}</span>
                        </div>
                        <h3 class="text-xl font-bold text-personal-navy">${edif.CALLE} ${edif.ALTURA}</h3>
                        ${htmlSecundarias}
                        <div class="my-3 p-3 bg-green-100 rounded border border-green-200">
                            <p class="text-green-800 font-bold text-sm">✅ ${datosRelevo.accion}</p>
                            <p class="text-green-700 text-xs mt-1">Relevado por: ${datosRelevo.tecnico}<br>Fecha: ${datosRelevo.fecha}</p>
                        </div>
                        <button onclick="deshacerRelevo('${edif.ACTIVO}')" class="w-full mt-2 text-sm text-red-600 font-semibold py-2 border border-red-200 rounded hover:bg-red-50">Deshacer / Editar</button>
                    `;
                } else {
                    const esConstruido = edif.ESTADO_CONSTRUCTIVO_EDIFICIO === "CONSTRUIDO";
                    let opcionesSelect = `
                        <option value="">Seleccione Acción...</option>
                        <option value="CORREGIR ALTURA">Corregir Altura</option>
                        <option value="UNIFICAR DIRECCIONES">Unificar Direcciones</option>
                        <option value="NO ESTA CONSTRUIDO">No está construido / Obra</option>
                    `;
                    if (!esConstruido) {
                        opcionesSelect += `
                            <option value="INFORMAR CONSTRUIDO">Informar Construido</option>
                            <option value="NO ES EDIFICIO">No es Edificio</option>
                            <option value="IMPOSIBLE CONSTRUIR">Imposible Construir</option>
                            <option value="COMPETENCIA">Competencia</option>
                        `;
                    }

                    card.innerHTML = `
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-xs font-bold text-gray-500">ID: ${edif.ACTIVO} | NAP: ${edif.NAP}</span>
                            <span class="text-[10px] font-bold bg-gray-200 text-gray-700 px-2 py-1 rounded tracking-wide">${edif.ESTADO_CONSTRUCTIVO_EDIFICIO}</span>
                        </div>
                        <h3 class="text-xl font-bold text-personal-navy">${edif.CALLE} ${edif.ALTURA}</h3>
                        <p class="text-xs text-gray-500 mb-2">${edif.CIUDAD}, ${edif.PARTIDO}</p>
                        ${htmlSecundarias}
                        
                        <div class="mt-4 space-y-2">
                            <select id="accion-${edif.ACTIVO}" class="w-full p-2.5 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-personal-cyan outline-none">
                                ${opcionesSelect}
                            </select>
                            <input type="text" id="obs-${edif.ACTIVO}" placeholder="Observación (Obligatoria)" class="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-personal-cyan outline-none">
                            
                            <div class="flex items-center justify-between bg-gray-50 border border-gray-200 p-2 rounded-lg">
                                <label class="text-xs font-semibold text-gray-600 w-1/3">Adjuntar Fotos:</label>
                                <input type="file" id="fotos-${edif.ACTIVO}" multiple accept="image/*" class="w-2/3 text-xs file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-personal-cyan file:text-white hover:file:bg-personal-hover">
                            </div>
                            
                            <button onclick="enviarRelevo('${edif.ACTIVO}')" class="w-full bg-personal-cyan text-white p-3 rounded-lg font-bold shadow-md hover:bg-personal-hover transition mt-2">ENVIAR RELEVAMIENTO</button>
                        </div>
                    `;
                }
                container.appendChild(card);
            }
        }

        window.enviarRelevo = async (activo) => {
            const accion = document.getElementById(`accion-${activo}`).value;
            const obs = document.getElementById(`obs-${activo}`).value;
            const inputFotos = document.getElementById(`fotos-${activo}`);
            
            if (!accion || !obs) { alert("Acción y observación son obligatorias."); return; }
            if (inputFotos.files.length > 8) { alert("Máximo 8 fotos permitidas."); return; }

            const btn = event.target;
            btn.innerText = "Procesando..."; 
            btn.classList.add('opacity-75', 'cursor-not-allowed');
            btn.disabled = true;

            try {
                let fotosB64 = [];
                for (let i = 0; i < inputFotos.files.length; i++) {
                    fotosB64.push(await comprimirImagen(inputFotos.files[i]));
                }

                const payload = {
                    fecha: new Date().toLocaleString("es-AR"), tecnico: usuarioActual.email,
                    activo: activo, accion: accion, observacion: obs, fotos: fotosB64
                };

                const response = await fetch(GAS_URL, { method: 'POST', body: JSON.stringify(payload) });
                const result = await response.json();
                
                if(result.status === "success") {
                    await setDoc(doc(db, "relevamientos", activo), {
                        fecha: payload.fecha, tecnico: payload.tecnico, accion: payload.accion, observacion: payload.observacion
                    });
                    aplicarFiltros(); 
                } else {
                    alert("Error en servidor: " + result.message);
                    btn.innerText = "ENVIAR RELEVAMIENTO"; btn.disabled = false; btn.classList.remove('opacity-75', 'cursor-not-allowed');
                }
            } catch (error) {
                alert("Error de conexión al enviar.");
                btn.innerText = "ENVIAR RELEVAMIENTO"; btn.disabled = false; btn.classList.remove('opacity-75', 'cursor-not-allowed');
            }
        };

        window.deshacerRelevo = async (activo) => {
            if(confirm("¿Deseas editar este relevamiento? Se borrará el estado actual.")) {
                await deleteDoc(doc(db, "relevamientos", activo));
                aplicarFiltros();
            }
        };

        function comprimirImagen(file) {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = (e) => {
                    const img = new Image();
                    img.src = e.target.result;
                    img.onload = () => {
                        const canvas = document.createElement('canvas');
                        const scaleSize = 800 / img.width;
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
        <div class="bg-white p-8 rounded-xl shadow border-t-4 border-yellow-400 text-center mx-4">
            <h2 class="text-xl font-bold mb-2">Acceso Pendiente</h2>
            <p class="text-sm">Requiere autorización del administrador.</p>
        </div>
    </div>

    <div id="app-screen" class="hidden max-w-md mx-auto bg-gray-100 min-h-screen flex flex-col">
        <div class="bg-personal-navy text-white px-4 py-3 sticky top-0 z-20 flex justify-between items-center border-b-4 border-personal-cyan">
            <div>
                <h1 class="font-bold tracking-wide">Telecom <span class="text-personal-cyan">Relevo</span></h1>
                <p id="user-email" class="text-[10px] text-gray-300"></p>
            </div>
            <button id="btn-logout" class="text-xs bg-white/10 px-3 py-1.5 rounded">Salir</button>
        </div>

        <div class="bg-white shadow-sm z-10 p-4 border-b">
            <div class="flex justify-between items-center mb-3">
                <h2 class="font-bold text-personal-navy text-sm">Buscador</h2>
                <span id="status-db" class="text-[10px] text-gray-400">Cargando...</span>
            </div>
            
            <div class="grid grid-cols-2 gap-3 mb-3">
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">Subregión</label>
                    <select id="filt-subregion" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm">
                        <option value="">Todas</option>
                        <option value="CAPITAL NORTE">Capital Norte</option>
                        <option value="CAPITAL SUR">Capital Sur</option>
                    </select>
                </div>
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">PD</label>
                    <input type="text" id="filt-pd" placeholder="Ej: VCRG" maxlength="4" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase">
                </div>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-3">
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">PC</label>
                    <input type="text" id="filt-pc" placeholder="Ej: VCRGB" maxlength="5" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase">
                </div>
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">NAP</label>
                    <input type="text" id="filt-nap" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase">
                </div>
            </div>

            <div class="grid grid-cols-2 gap-3 mb-4">
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">Calle</label>
                    <input type="text" id="filt-calle" placeholder="Nombre" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm uppercase">
                </div>
                <div>
                    <label class="block text-[10px] font-bold text-gray-500 uppercase">Altura</label>
                    <input type="number" id="filt-altura" placeholder="Ej: 33" class="w-full mt-1 p-2 border rounded bg-gray-50 text-sm">
                </div>
            </div>

            <button onclick="aplicarFiltros()" class="w-full bg-personal-navy text-white font-bold py-2.5 rounded shadow">BUSCAR DIRECCIONES</button>
        </div>

        <div class="bg-gray-100 flex-1 p-4 pb-20">
            <p id="resultados-count" class="text-xs text-gray-500 font-bold mb-3 text-center uppercase tracking-wider">Use los filtros para buscar</p>
            <div id="cards-container"></div>
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