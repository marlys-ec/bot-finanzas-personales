import os
import subprocess
import speech_recognition as sr
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# Cargar configuración
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
recognizer = sr.Recognizer()

# Configurar Google Sheets
def setup_google_sheets():
    """Configura la conexión con Google Sheets"""
    try:
        # Scope para Google Sheets
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Autenticación
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        client = gspread.authorize(creds)
        
        # ABRE TU SHEET - REEMPLAZA ESTA URL CON LA DE TU SHEET
        sheet_url = "https://docs.google.com/spreadsheets/d/1Pv_nev-zcivlPafktC0A-w6eiKpzxYelID4A_Coqk5M/edit?gid=0#gid=0"  # ← CAMBIA ESTO
        spreadsheet = client.open_by_url(sheet_url)
        
        # Obtener la hoja "REGISTRO"
        worksheet = spreadsheet.worksheet("REGISTRO")
        
        print("✅ Google Sheets conectado correctamente")
        return worksheet
    except Exception as e:
        print(f"❌ Error conectando con Google Sheets: {e}")
        return None

# Variable global para la hoja de cálculo
worksheet = setup_google_sheets()

def convert_ogg_to_wav(ogg_path, wav_path):
    """Convierte archivo OGG a WAV usando ffmpeg"""
    try:
        command = [
            'ffmpeg', '-i', ogg_path, 
            '-acodec', 'pcm_s16le', 
            '-ac', '1', 
            '-ar', '16000', 
            wav_path,
            '-y'
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error en conversión: {e}")
        return False

def detect_type_and_category(text):
    """Detecta tipo (INCOME/EXPENSE) y categoría por separado"""
    text_lower = text.lower()
    
    # === 1. DETECTAR TIPO CON PALABRAS CLAVE FUERTES ===
    expense_words = ['gasté', 'compré', 'pagué', 'gasto', 'compro', 'pago', 'usé']
    income_words = ['ingresé', 'gané', 'recibí', 'saldo inicial', 'ingreso', 'ganancia', 'deposite', 'cobré', 'cobre']
    
    # PRIORIDAD ABSOLUTA: Si encuentra palabras de INCOME, es INCOME
    if any(word in text_lower for word in income_words):
        transaction_type = "INCOME"
    # Si encuentra palabras de EXPENSE, es EXPENSE  
    elif any(word in text_lower for word in expense_words):
        transaction_type = "EXPENSE"
    else:
        transaction_type = "EXPENSE"  # Por defecto
    
    # === 2. DETECTAR CATEGORÍA (BUSCAR PALABRAS COMPLETAS) ===
    
    # Dividir el texto en palabras individuales
    words = text_lower.split()
    print(f"🔍 Palabras detectadas: {words}")
    
    # **BUSCAR PALABRAS COMPLETAS, NO SUBSTRINGS**
    if any(word in ['comida', 'carne', 'huevos', 'leche', 'chocolate', 'chucherías', 'pan', 'tienda', 'tiendita', 'alimentos', 'dulces', 'walmart', 'chedraui', 'carnicería', 'soriana'] for word in words):
        category = "Alimentos"
    elif any(word in ['transporte', 'gasolina', 'uber', 'taxi', 'metro', 'bus', 'camión', 'gas', 'estacionamiento', 'carro'] for word in words):
        category = "Transporte"
    elif any(word in ['uñas', 'keratina', 'pelo', 'peluquería', 'cremas', 'skin', 'care', 'maquillaje', 'perfume', 'manicura', 'pedicura', 'cejas', 'pestañas', 'facial', 'belleza'] for word in words):
        category = "Belleza"
    elif any(word in ['internet', 'wifi', 'conexion'] for word in words):
        category = "Internet"
    elif any(word in ['taekwondo', 'uniformes', 'competencia', 'artes', 'marciales', 'evaluna'] for word in words):
        category = "Taekwondo"
    elif any(word in ['escuela', 'materiales', 'cuota', 'tarea', 'merienda', 'uniformes', 'zapatos', 'mochila', 'impresiones'] for word in words):
        category = "Escuela"
    elif any(word in ['cine', 'pizza', 'didi', 'paseo', 'viajes', 'vacaciones', 'hotel', 'parque', 'juguete', 'juegos', 'capricho', 'ocio', 'placer'] for word in words):
        category = "Ocio y placer"
    elif any(word in ['amazon', 'mercado', 'libre', 'temu', 'shein', 'online'] for word in words):
        category = "Compras online"
    elif any(word in ['netflix', 'spotify', 'youtube', 'hbo', 'disney', 'canva', 'suscripción'] for word in words):
        category = "Suscripciones"
    elif any(word in ['inversión', 'bolsa', 'cripto', 'acciones', 'ahorro'] for word in words):
        category = "Inversiones"
    elif any(word in ['casa', 'renta', 'hipoteca', 'mantenimiento', 'reparación', 'mueble', 'electrodoméstico'] for word in words):
        category = "Casa"
    elif any(word in ['luz', 'agua', 'electricidad', 'teléfono', 'celular'] for word in words):
        category = "Casa"
    elif any(word in ['salario', 'trabajo', 'nómina', 'empleo', 'sueldo'] for word in words):
        category = "Trabajo"
    elif any(word in ['freelance', 'extra', 'proyecto', 'cliente', 'independiente'] for word in words):
        category = "Extra"
    elif any(word in ['doctor', 'médico', 'seguro', 'hospital', 'farmacia', 'medicina', 'vitaminas', 'consulta', 'suplementos', 'dentista', 'salud'] for word in words):
        category = "Salud"
    elif any(word in ['gas', 'servicios'] for word in words):
        category = "Servicios"
    else:
        category = "Otros"
    
    print(f"🏷️ Categoría asignada: {category}")
    return transaction_type, category

def extract_amount(text):
    """Extrae el monto - MANEJA ESPACIOS EN NÚMEROS GRANDES"""
    import re
    
    print(f"🔍 Buscando monto en: '{text}'")
    
    # **PRIMERO: Buscar números con espacios (53 000, 33 250)**
    space_pattern = r'\b(\d{1,3}(?:\s\d{3})+\b)'
    space_matches = re.findall(space_pattern, text)
    
    if space_matches:
        # Quitar espacios y convertir
        amount_str = space_matches[0].replace(' ', '')
        amount = int(amount_str)
        print(f"💰 Monto con espacios detectado: ${amount}")
        return amount
    
    # **SEGUNDO: Buscar cualquier secuencia de dígitos (33000, 50000)**
    digit_pattern = r'\b(\d{4,})\b'  # Solo números de 4+ dígitos
    digit_matches = re.findall(digit_pattern, text)
    
    if digit_matches:
        amount = int(digit_matches[0])
        print(f"💰 Monto grande detectado: ${amount}")
        return amount
    
    # **TERCERO: Búsqueda general (último recurso)**
    all_digits = re.findall(r'\d+', text)
    if all_digits:
        # Tomar el número más grande
        largest = max([int(num) for num in all_digits])
        print(f"💰 Monto general detectado: ${largest}")
        return largest
    
    print("❌ No se pudo extraer monto")
    return None

async def save_to_sheet(date, transaction_type, category, description, amount):
    """Guarda la transacción en Google Sheets - MÉTODO DIRECTO"""
    try:
        if worksheet is None:
            print("❌ No hay conexión con Google Sheets")
            return False
        
        # Preparar datos
        row = [date, transaction_type, category, description, amount]
        print(f"🔄 Guardando: {row}")
        
        # **MÉTODO DIRECTO: OBTENER TODOS LOS DATOS Y AGREGAR MANUALMENTE**
        all_data = worksheet.get_all_values()
        
        # Si solo hay encabezados, empezar en fila 2
        if len(all_data) <= 1:
            next_row = 2
        else:
            # Buscar la primera fila completamente vacía DESPUÉS de los encabezados
            next_row = len(all_data) + 1
            for i in range(1, len(all_data)):
                # Si la fila está completamente vacía
                if not any(cell.strip() for cell in all_data[i] if cell):
                    next_row = i + 1
                    break
        
        print(f"📝 Escribiendo en fila: {next_row}")
        
        # Escribir directamente
        worksheet.update(f'A{next_row}:E{next_row}', [row])
        print(f"✅ Guardado exitosamente en fila {next_row}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def handle_voice_message(update: Update, context):
    """Función que se ejecuta cuando recibes un mensaje de voz"""
    user_name = update.message.from_user.first_name
    print(f"🎤 Mensaje de voz recibido de {user_name}")
    
    audio_path = None
    wav_path = None
    
    try:
        # Obtener y descargar audio
        voice_file = await update.message.voice.get_file()
        audio_path = f"temp_audio_{user_name}.oga"
        await voice_file.download_to_drive(audio_path)
        print(f"💾 Audio descargado")
        
        # Convertir a WAV
        wav_path = audio_path.replace(".oga", ".wav")
        print("🔄 Convirtiendo audio...")
        
        if not convert_ogg_to_wav(audio_path, wav_path):
            raise Exception("Error en conversión con FFmpeg")
        
        print("✅ Audio convertido")
        
        # TRANSCRIBIR
        print("🔊 Transcribiendo...")
        with sr.AudioFile(wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)
            transcribed_text = recognizer.recognize_google(audio_data, language="es-ES")
        
        print(f"📝 Texto: '{transcribed_text}'")
        
        # PROCESAR Y GUARDAR
        transaction_type, category = detect_type_and_category(transcribed_text)
        amount = extract_amount(transcribed_text)
        
        if amount is None:
            response = f"❌ {user_name}, no pude detectar el monto en: '{transcribed_text}'\n\n💡 Ejemplo: 'gasté 100 en supermercado'"
            await update.message.reply_text(response)
            return  # ← IMPORTANTE: esto detiene la función aquí
        else:
            # Formatear monto (negativo para gastos)
            formatted_amount = -amount if transaction_type == "EXPENSE" else amount
            
            # Guardar en Google Sheets
            current_date = datetime.now().strftime("%Y-%m-%d")
            success = await save_to_sheet(
                current_date,
                transaction_type,
                category,
                transcribed_text,
                formatted_amount
            )
            
            if success:
                response = f"✅ {user_name}, guardé en tu Sheet:\n{transaction_type} | {category} | ${amount}"
            else:
                response = f"❌ {user_name}, guardé la transcripción pero no pude guardar en el Sheet"
        
        await update.message.reply_text(response)
        
    except sr.UnknownValueError:
        print("❌ No se pudo entender el audio")
        await update.message.reply_text("🔇 No pude entender el audio. ¿Podrías hablar más claro?")
    except sr.RequestError as e:
        print(f"❌ Error de conexión: {e}")
        await update.message.reply_text("🌐 Error de conexión. Verifica tu internet.")
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text(f"❌ Error técnico: {str(e)}")
    finally:
        # Limpiar
        for path in [audio_path, wav_path]:
            if path and os.path.exists(path):
                os.remove(path)
                print(f"🧹 Eliminado: {path}")

async def handle_text_message(update: Update, context):
    """Función para mensajes de texto"""
    user_message = update.message.text
    user_name = update.message.from_user.first_name
    print(f"📩 Texto de {user_name}: '{user_message}'")
    
    try:
        # Detectar si es un gasto/ingreso
        transaction_type, category = detect_type_and_category(user_message)
        amount = extract_amount(user_message)
        
        if amount is None:
            response = f"✅ {user_name}, recibí: '{user_message}'\n\n💡 Tip: Para registrar gastos, escribe: 'gasté 500 en supermercado'"
        else:
            # Formatear monto
            formatted_amount = -amount if transaction_type == "EXPENSE" else amount
            
            # Guardar en Google Sheets
            current_date = datetime.now().strftime("%Y-%m-%d")
            success = await save_to_sheet(
                current_date,
                transaction_type,
                category,
                user_message,
                formatted_amount
            )
            
            if success:
                response = f"💰 {user_name}, ¡guardé en tu Sheet!\n{transaction_type} | {category} | ${amount}"
            else:
                response = f"✅ {user_name}, recibí: '{user_message}' (pero no pude guardar en el Sheet)"
    
    except Exception as e:
        print(f"❌ Error procesando texto: {e}")
        response = f"✅ {user_name}, recibí: '{user_message}'"
    
    await update.message.reply_text(response)

def main():
    print("🤖 Iniciando bot con GOOGLE SHEETS...")
    
    # Verificar FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("✅ FFmpeg funcionando correctamente")
    except:
        print("❌ FFmpeg no disponible")
        return
    
    # Verificar Google Sheets
    if worksheet is None:
        print("❌ No se pudo conectar con Google Sheets")
        return
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(MessageHandler(filters.TEXT, handle_text_message))
    
    print("🎉 Bot listo! Envía audios o textos con tus gastos/ingresos...")
    application.run_polling()

import os

if __name__ == "__main__":
    # Para Render.com - usa el PORT que proporcionan
    port = int(os.environ.get('PORT', 8443))
    
    # Iniciar el bot
    try:
        main()
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")