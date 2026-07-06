import flet as ft
import psycopg2
import threading
import time
import os
from datetime import datetime, timedelta

# COLE A SUA URL DO SUPABASE AQUI TAMBÉM!
URL_SUPABASE = "postgresql://postgres.qvgxlpnicbjgnierhbvi:supleweb26%40@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"

def conectar_banco():
    return psycopg2.connect(URL_SUPABASE)

def tarefa_se_aplica(recorrencia, data_alvo: datetime):
    dia_da_semana = data_alvo.weekday()
    hoje_e_fds = dia_da_semana in [5, 6]
    
    if recorrencia == "todo_dia":
        return True
    
    if recorrencia == "exceto_fds" and not hoje_e_fds:
        return True
        
    if recorrencia == "apenas_fds" and hoje_e_fds:
        return True
        
    if "," in recorrencia or recorrencia.isdigit():
        if str(dia_da_semana) in recorrencia.split(","):
            return True
            
    return False

def main(page: ft.Page):
    page.title = "Super Rotina"
    page.theme_mode = ft.ThemeMode.DARK
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER 
    page.scroll = ft.ScrollMode.AUTO 

    estado_app = {
        "usuario": None,
        "data_dashboard": datetime.now()
    }

    # ==========================================
    # TELA DE LOGIN 
    # ==========================================
    campo_login = ft.TextField(
        label="Digite seu nome (sempre o mesmo)", 
        width=300, 
        border_color=ft.Colors.GREEN_700,
        text_align=ft.TextAlign.CENTER,
        autofocus=True,
        capitalization=ft.TextCapitalization.CHARACTERS 
    )

    def entrar_app(e):
        nome_digitado = campo_login.value.strip().upper() 
        if nome_digitado:
            # Verifica se o usuário é novo ou antigo antes de abrir a tela
            conexao = conectar_banco()
            cursor = conexao.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM tarefas WHERE usuario = %s", (nome_digitado,))
            tem_tarefas = cursor.fetchone()[0] > 0
            
            cursor.execute("SELECT COUNT(*) FROM gratidao WHERE usuario = %s", (nome_digitado,))
            tem_gratidao = cursor.fetchone()[0] > 0
            
            conexao.close()
            
            is_novo_usuario = not (tem_tarefas or tem_gratidao)

            # Define o estado e limpa a tela para carregar o app
            estado_app["usuario"] = nome_digitado
            page.controls.clear()
            page.vertical_alignment = ft.MainAxisAlignment.START 
            
            page.add(
                cabecalho,      
                ft.Divider(),
                linha_abas_custom,    
                visual_atual          
            )
            
            carregar_tarefas()
            
            thread_relogio = threading.Thread(target=atualizar_relogio, daemon=True)
            thread_relogio.start()
            
            # Mostra o feedback de login para o usuário
            if is_novo_usuario:
                page.snack_bar = ft.SnackBar(ft.Text(f"🎉 Novo perfil '{nome_digitado}' criado com sucesso!"), bgcolor=ft.Colors.GREEN_800)
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"👋 Bem-vindo de volta, {nome_digitado}!"), bgcolor=ft.Colors.BLUE_800)
                
            page.snack_bar.open = True
            page.update()

    botao_entrar = ft.FilledButton(
        "Entrar na Super Rotina", 
        on_click=entrar_app, 
        bgcolor=ft.Colors.GREEN_700
    )
    
    tela_login = ft.Column(
        controls=[
            ft.Text("✅ Super Rotina", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("A Central de Hábitos da Família", color=ft.Colors.GREY_400),
            ft.Container(height=20),
            campo_login,
            botao_entrar
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    # ==========================================
    # LÓGICA PRINCIPAL DO APLICATIVO
    # ==========================================

    salvar_arquivo_dialog = ft.FilePicker()
    page.services.append(salvar_arquivo_dialog)

    async def exportar_diario(e):
        mes_atual = datetime.now().strftime("%Y-%m")
        usuario = estado_app["usuario"]
        try:
            path = await salvar_arquivo_dialog.save_file_async(
                file_name=f"{usuario}_gratidao_{mes_atual}.txt", 
                allowed_extensions=["txt"]
            )
        except AttributeError:
            path = await salvar_arquivo_dialog.save_file(
                file_name=f"{usuario}_gratidao_{mes_atual}.txt", 
                allowed_extensions=["txt"]
            )
            
        if path:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute(
                "SELECT data, mensagem FROM gratidao WHERE usuario = %s AND data LIKE %s ORDER BY data ASC", 
                (usuario, f"{mes_atual}-%")
            )
            registros = cursor.fetchall()
            conexao.close()
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Diário da Gratidão - {usuario} - {mes_atual}\n")
                f.write("="*40 + "\n\n")
                for data_str, msg in registros:
                    data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                    f.write(f"[{data_br}]\n{msg}\n\n")
            
            page.snack_bar = ft.SnackBar(ft.Text("Diário exportado com sucesso!"), bgcolor=ft.Colors.GREEN_800)
            page.snack_bar.open = True
            page.update()

    relogio_digital = ft.Text(
        value="", 
        size=16, 
        weight=ft.FontWeight.BOLD, 
        color=ft.Colors.GREEN_ACCENT, 
        style=ft.TextStyle(font_family="Courier New")
    )
    
    texto_ofensiva = ft.Text(
        value="🔥 0 dias", 
        size=16, 
        weight=ft.FontWeight.BOLD, 
        color=ft.Colors.ORANGE_500
    )
    
    cabecalho = ft.Row(
        controls=[relogio_digital, texto_ofensiva], 
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN, 
        width=480
    )
    
    DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

    def calcular_ofensiva():
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        streak = 0
        hoje = datetime.now()

        cursor.execute("SELECT id, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_tarefas = cursor.fetchall()

        for i in range(365): 
            data_alvo = hoje - timedelta(days=i)
            data_str = data_alvo.strftime("%Y-%m-%d")

            total_tarefas = 0
            for _, rec in todas_tarefas:
                if tarefa_se_aplica(rec, data_alvo):
                    total_tarefas += 1
                    
            total_esperado = total_tarefas + 1 

            cursor.execute(
                "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1", 
                (usuario, data_str)
            )
            feitos = cursor.fetchone()[0]

            cursor.execute(
                "SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", 
                (usuario, data_str)
            )
            row = cursor.fetchone()
            if row and len(row[0].split()) > 3:
                feitos += 1

            if total_esperado > 0 and feitos >= total_esperado:
                streak += 1
            elif i == 0:
                pass
            else:
                break 

        conexao.close()
        return streak

    def atualizar_relogio():
        while True:
            try:
                agora = datetime.now()
                data_formatada = agora.strftime("%d/%m/%Y")
                dia_nome = DIAS_SEMANA[agora.weekday()]
                hora_formatada = agora.strftime("%H:%M:%S")
                
                relogio_digital.value = f"👤 {estado_app['usuario']} | 🗓️ {data_formatada} | ⏰ {hora_formatada}"
                page.update()
                time.sleep(1)
            except:
                break

    lista_tarefas = ft.Column()

    def alternar_check(e, id_tarefa):
        usuario = estado_app["usuario"]
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        if e.control.value == True:
            cursor.execute(
                "INSERT INTO historico_checks (usuario, tarefa_id, data, pago) VALUES (%s, %s, %s, 1)", 
                (usuario, id_tarefa, data_hoje)
            )
        else:
            cursor.execute(
                "DELETE FROM historico_checks WHERE usuario = %s AND tarefa_id = %s AND data = %s", 
                (usuario, id_tarefa, data_hoje)
            )
            
        conexao.commit()
        conexao.close()
        atualizar_streak_ui()

    def deletar_tarefa(e, id_tarefa):
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM tarefas WHERE id = %s", (id_tarefa,))
        cursor.execute("DELETE FROM historico_checks WHERE tarefa_id = %s", (id_tarefa,))
        conexao.commit()
        conexao.close()
        carregar_tarefas()

    def abrir_dialogo_edicao(e, id_tarefa, nome_atual, recorrencia_atual):
        campo_nome_edit = ft.TextField(
            label="Nome da Tarefa", 
            value=nome_atual, 
            width=300, 
            border_color=ft.Colors.BLUE_400
        )
        
        if "," in recorrencia_atual or recorrencia_atual.isdigit():
            valor_dropdown_atual = "especifico"
        else:
            valor_dropdown_atual = recorrencia_atual
        
        seletor_rec_edit = ft.Dropdown(
            label="Recorrência", 
            width=300, 
            value=valor_dropdown_atual, 
            border_color=ft.Colors.BLUE_400,
            options=[
                ft.dropdown.Option("todo_dia", "Todo dia"),
                ft.dropdown.Option("exceto_fds", "Dias de Semana"), 
                ft.dropdown.Option("apenas_fds", "Finais de Semana"),
                ft.dropdown.Option("especifico", "Dias Específicos (Requer recriar)"), 
            ]
        )

        def salvar_alteracoes(e):
            novo_nome = campo_nome_edit.value.strip()
            nova_recorrencia = seletor_rec_edit.value
            
            if nova_recorrencia == "especifico" and valor_dropdown_atual != "especifico": 
                nova_recorrencia = "todo_dia" 
            elif valor_dropdown_atual == "especifico" and nova_recorrencia == "especifico": 
                nova_recorrencia = recorrencia_atual 

            if novo_nome != "":
                conexao = conectar_banco()
                cursor = conexao.cursor()
                cursor.execute(
                    "UPDATE tarefas SET nome = %s, recorrencia = %s WHERE id = %s", 
                    (novo_nome, nova_recorrencia, id_tarefa)
                )
                conexao.commit()
                conexao.close()
                dialogo.open = False
                carregar_tarefas()

        def cancelar_edicao(e):
            dialogo.open = False
            page.update()

        dialogo = ft.AlertDialog(
            title=ft.Text("✏️ Editar Tarefa"),
            content=ft.Column([campo_nome_edit, seletor_rec_edit], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=cancelar_edicao, style=ft.ButtonStyle(color=ft.Colors.RED_400)),
                ft.TextButton("Salvar", on_click=salvar_alteracoes, style=ft.ButtonStyle(color=ft.Colors.BLUE_400)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        page.dialog = dialogo
        dialogo.open = True
        page.update()

    def atualizar_streak_ui():
        texto_ofensiva.value = f"🔥 {calcular_ofensiva()} dias"
        page.update()

    def carregar_tarefas():
        lista_tarefas.controls.clear()
        agora = datetime.now()
        data_hoje = agora.strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, nome, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_as_tarefas = cursor.fetchall()
        
        for id_tarefa, nome_tarefa, recorrencia in todas_as_tarefas:
            if not tarefa_se_aplica(recorrencia, agora): 
                continue

            cursor.execute(
                "SELECT id FROM historico_checks WHERE usuario = %s AND tarefa_id = %s AND data = %s AND pago = 1", 
                (usuario, id_tarefa, data_hoje)
            )
            ja_feito = cursor.fetchone() is not None
            
            checkbox = ft.Checkbox(
                label=nome_tarefa, 
                value=ja_feito, 
                on_change=lambda e, id_t=id_tarefa: alternar_check(e, id_t)
            )
            
            botao_editar = ft.IconButton(
                icon=ft.Icons.EDIT_OUTLINED, 
                icon_color=ft.Colors.BLUE_400, 
                on_click=lambda e, id_t=id_tarefa, n=nome_tarefa, r=recorrencia: abrir_dialogo_edicao(e, id_t, n, r)
            )
            
            botao_lixo = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, 
                icon_color=ft.Colors.RED_400, 
                on_click=lambda e, id_t=id_tarefa: deletar_tarefa(e, id_t)
            )
            
            botoes_acao = ft.Row(
                controls=[botao_editar, botao_lixo], 
                spacing=0
            )
            
            linha_tarefa = ft.Row(
                controls=[checkbox, botoes_acao], 
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN, 
                width=450
            )
            
            lista_tarefas.controls.append(linha_tarefa)
            
        cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
        row = cursor.fetchone()
        campo_gratidao_hoje.value = row[0] if row else ""
        
        conexao.close()
        atualizar_streak_ui()
        page.update()

    chk_seg = ft.Checkbox(label="Seg", value=False)
    chk_ter = ft.Checkbox(label="Ter", value=False)
    chk_qua = ft.Checkbox(label="Qua", value=False)
    chk_qui = ft.Checkbox(label="Qui", value=False)
    chk_sex = ft.Checkbox(label="Sex", value=False)
    chk_sab = ft.Checkbox(label="Sáb", value=False)
    chk_dom = ft.Checkbox(label="Dom", value=False)
    
    lista_chks_dias = [chk_seg, chk_ter, chk_qua, chk_qui, chk_sex, chk_sab, chk_dom]
    
    linha_dias_semana = ft.Row(
        controls=lista_chks_dias, 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=5, 
        visible=False
    )

    def monitorar_dropdown_recorrencia(e):
        if seletor_recorrencia.value == "especifico":
            linha_dias_semana.visible = True
        else:
            linha_dias_semana.visible = False
        page.update()

    def adicionar_tarefa(e):
        texto_digitado = campo_nova_tarefa.value.strip()
        recorrencia_escolhida = seletor_recorrencia.value
        usuario = estado_app["usuario"]

        if texto_digitado != "":
            if recorrencia_escolhida == "especifico":
                dias_finais = []
                for i, chk in enumerate(lista_chks_dias):
                    if chk.value:
                        dias_finais.append(str(i))
                        
                if dias_finais:
                    recorrencia_salvar = ",".join(dias_finais) 
                else:
                    recorrencia_salvar = "todo_dia"
            else:
                recorrencia_salvar = recorrencia_escolhida

            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute(
                "INSERT INTO tarefas (usuario, nome, recorrencia) VALUES (%s, %s, %s)", 
                (usuario, texto_digitado, recorrencia_salvar)
            )
            conexao.commit()
            conexao.close()

            for chk in lista_chks_dias: 
                chk.value = False
                
            linha_dias_semana.visible = False
            seletor_recorrencia.value = "todo_dia"
            campo_nova_tarefa.value = ""
            carregar_tarefas()

    campo_gratidao_hoje = ft.TextField(
        label="Pelo que você é grato hoje? (mín. 4 palavras p/ pontuar)",
        multiline=True, 
        min_lines=2, 
        max_lines=3, 
        border_color=ft.Colors.GREEN_700, 
        width=450
    )

    def salvar_gratidao(e):
        texto = campo_gratidao_hoje.value.strip()
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        if texto:
            cursor.execute("""
                INSERT INTO gratidao (usuario, data, mensagem) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (usuario, data) 
                DO UPDATE SET mensagem = EXCLUDED.mensagem
            """, (usuario, data_hoje, texto))
            page.snack_bar = ft.SnackBar(ft.Text("Gratidão salva com sucesso!"), bgcolor=ft.Colors.GREEN_800)
        else:
            cursor.execute("DELETE FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_hoje))
            page.snack_bar = ft.SnackBar(ft.Text("Gratidão removida."), bgcolor=ft.Colors.GREY_800)
            
        conexao.commit()
        conexao.close()
        atualizar_streak_ui()
        page.snack_bar.open = True
        page.update()

    botao_salvar_gratidao = ft.FilledButton(
        "Salvar Gratidão", 
        on_click=salvar_gratidao, 
        bgcolor=ft.Colors.GREEN_700
    )
    
    container_gratidao = ft.Container(
        content=ft.Column(
            [campo_gratidao_hoje, botao_salvar_gratidao], 
            alignment=ft.MainAxisAlignment.CENTER, 
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        ),
        padding=15, 
        border_radius=10, 
        bgcolor=ft.Colors.GREY_900, 
        border=ft.Border.all(1, ft.Colors.GREY_800), 
        width=480
    )

    texto_titulo = ft.Text(value="✅ Super Rotina", size=28, weight=ft.FontWeight.BOLD)
    texto_subtitulo = ft.Text("Seus Checks favoritos em um só lugar!", size=14, color=ft.Colors.GREY_400)
    
    campo_nova_tarefa = ft.TextField(
        hint_text="O que precisamos checar hoje?", 
        width=230, 
        border_color=ft.Colors.GREEN_700
    )
    
    seletor_recorrencia = ft.Dropdown(
        width=150, 
        value="todo_dia", 
        border_color=ft.Colors.GREEN_700, 
        on_select=monitorar_dropdown_recorrencia, 
        options=[
            ft.dropdown.Option("todo_dia", "Todo dia"),
            ft.dropdown.Option("exceto_fds", "Dias de Semana"), 
            ft.dropdown.Option("apenas_fds", "Finais de Semana"),
            ft.dropdown.Option("especifico", "Dias Específicos"),
        ]
    )
    
    botao_adicionar = ft.FilledButton(
        content=ft.Text(value="Adicionar", color=ft.Colors.WHITE), 
        on_click=adicionar_tarefa, 
        bgcolor=ft.Colors.GREEN_700
    )
    
    linha_input = ft.Row(
        controls=[campo_nova_tarefa, seletor_recorrencia, botao_adicionar], 
        alignment=ft.MainAxisAlignment.CENTER
    )

    conteudo_checklist = ft.Column(
        controls=[
            ft.Divider(), 
            texto_titulo, 
            texto_subtitulo, 
            ft.Divider(), 
            linha_input, 
            linha_dias_semana, 
            ft.Divider(), 
            lista_tarefas, 
            ft.Divider(), 
            container_gratidao
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    conteudo_dashboard = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    texto_data_dashboard = ft.Text("Hoje", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)

    def mudar_data_dashboard(delta):
        nova_data = estado_app["data_dashboard"] + timedelta(days=delta)
        if nova_data.date() <= datetime.now().date():
            estado_app["data_dashboard"] = nova_data
            atualizar_dashboard()

    btn_relogio_voltar = ft.IconButton(
        icon=ft.Icons.ARROW_BACK_IOS, 
        icon_color=ft.Colors.BLUE_400, 
        on_click=lambda e: mudar_data_dashboard(-1)
    )
    
    btn_relogio_avancar = ft.IconButton(
        icon=ft.Icons.ARROW_FORWARD_IOS, 
        icon_color=ft.Colors.BLUE_400, 
        on_click=lambda e: mudar_data_dashboard(1)
    )
    
    linha_maquina_tempo = ft.Row(
        controls=[btn_relogio_voltar, texto_data_dashboard, btn_relogio_avancar], 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=20
    )

    def criar_card_pizza(titulo, porcentagem):
        valor_anel = porcentagem / 100.0 
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(titulo, size=16, weight=ft.FontWeight.BOLD),
                    ft.Stack(
                        controls=[
                            ft.ProgressRing(
                                value=valor_anel, 
                                stroke_width=10, 
                                color=ft.Colors.GREEN_ACCENT_400, 
                                bgcolor=ft.Colors.GREY_800, 
                                width=90, 
                                height=90
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [ft.Text(f"{int(porcentagem)}%", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT)], 
                                    alignment=ft.MainAxisAlignment.CENTER, 
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                                ),
                                width=90, 
                                height=90
                            )
                        ]
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ), 
            bgcolor=ft.Colors.GREY_900, 
            padding=15, 
            border_radius=12, 
            width=140, 
            border=ft.Border.all(1, ft.Colors.GREY_800)
        )

    def checar_gratidao_dia(cursor, usuario, data_str):
        cursor.execute("SELECT mensagem FROM gratidao WHERE usuario = %s AND data = %s", (usuario, data_str))
        row = cursor.fetchone()
        if row and len(row[0].split()) > 3: 
            return 1, row[0]
        return 0, ""

    def atualizar_dashboard():
        conteudo_dashboard.controls.clear()
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        data_alvo = estado_app["data_dashboard"]
        hoje_real = datetime.now()
        
        if data_alvo.date() == hoje_real.date():
            texto_data_dashboard.value = "Hoje"
            btn_relogio_avancar.disabled = True
        else:
            texto_data_dashboard.value = data_alvo.strftime("%d/%m/%Y")
            btn_relogio_avancar.disabled = False
            
        data_str = data_alvo.strftime("%Y-%m-%d")
        
        cursor.execute("SELECT id, recorrencia FROM tarefas WHERE usuario = %s", (usuario,))
        todas_as_tarefas = cursor.fetchall()
        
        total_tarefas_alvo = 0
        for _, rec in todas_as_tarefas:
            if tarefa_se_aplica(rec, data_alvo):
                total_tarefas_alvo += 1
                
        cursor.execute("SELECT MIN(data) FROM historico_checks WHERE usuario = %s AND pago = 1", (usuario,))
        resultado_min = cursor.fetchone()
        
        if resultado_min and resultado_min[0]:
            primeira_data_str = resultado_min[0]
        else:
            primeira_data_str = data_str
            
        data_inicio = datetime.strptime(primeira_data_str, "%Y-%m-%d")
        dias_desde_o_inicio = max(1, (data_alvo - data_inicio).days + 1)
            
        cursor.execute(
            "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data = %s AND pago = 1", 
            (usuario, data_str)
        )
        feitos_hoje_tarefas = cursor.fetchone()[0]
        
        total_hoje = total_tarefas_alvo + 1 
        gratidao_pontua, texto_gratidao_passado = checar_gratidao_dia(cursor, usuario, data_str)
        feitos_hoje = feitos_hoje_tarefas + gratidao_pontua
        
        if total_hoje > 0:
            pct_diario = (feitos_hoje / total_hoje) * 100
        else:
            pct_diario = 0.0

        sete_dias_atras = (data_alvo - timedelta(days=7)).strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data >= %s AND data <= %s AND pago = 1", 
            (usuario, sete_dias_atras, data_str)
        )
        feitos_semana_tarefas = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT mensagem FROM gratidao WHERE usuario = %s AND data >= %s AND data <= %s", 
            (usuario, sete_dias_atras, data_str)
        )
        gratidoes_semana = 0
        for (msg,) in cursor.fetchall():
            if len(msg.split()) > 3:
                gratidoes_semana += 1
                
        dias_validos_semana = min(7, dias_desde_o_inicio)
        total_esperado_semana = total_hoje * dias_validos_semana
        
        if total_esperado_semana > 0:
            pct_semanal = ((feitos_semana_tarefas + gratidoes_semana) / total_esperado_semana) * 100
        else:
            pct_semanal = pct_diario

        trinta_dias_atras = (data_alvo - timedelta(days=30)).strftime("%Y-%m-%d")
        cursor.execute(
            "SELECT COUNT(*) FROM historico_checks WHERE usuario = %s AND data >= %s AND data <= %s AND pago = 1", 
            (usuario, trinta_dias_atras, data_str)
        )
        feitos_mes_tarefas = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT mensagem FROM gratidao WHERE usuario = %s AND data >= %s AND data <= %s", 
            (usuario, trinta_dias_atras, data_str)
        )
        gratidoes_mes = 0
        for (msg,) in cursor.fetchall():
            if len(msg.split()) > 3:
                gratidoes_mes += 1
                
        dias_validos_mes = min(30, dias_desde_o_inicio)
        total_esperado_mes = total_hoje * dias_validos_mes
        
        if total_esperado_mes > 0:
            pct_mensal = ((feitos_mes_tarefas + gratidoes_mes) / total_esperado_mes) * 100
        else:
            pct_mensal = pct_diario

        conexao.close()

        linha_graficos = ft.Row(
            controls=[
                criar_card_pizza("Diário", pct_diario), 
                criar_card_pizza("Semanal", pct_semanal), 
                criar_card_pizza("Mensal", pct_mensal)
            ], 
            alignment=ft.MainAxisAlignment.CENTER, 
            spacing=10
        )
        
        box_gratidao_passado = ft.Container(visible=False)
        if data_alvo.date() != hoje_real.date() and texto_gratidao_passado:
            box_gratidao_passado = ft.Container(
                content=ft.Column([
                    ft.Text(f"Sua gratidão neste dia:", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200), 
                    ft.Text(f"'{texto_gratidao_passado}'", italic=True)
                ]),
                bgcolor=ft.Colors.GREY_900, 
                padding=15, 
                border_radius=10, 
                width=440
            )

        conteudo_dashboard.controls.extend([
            ft.Divider(), 
            linha_maquina_tempo, 
            ft.Container(height=10), 
            ft.Text("🏆 Central de Metas", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("Complete os anéis e vença mais um dia!", size=14, color=ft.Colors.GREY_400), 
            ft.Container(height=20), 
            linha_graficos, 
            ft.Container(height=10), 
            box_gratidao_passado
        ])
        
        page.update()

    conteudo_diario = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def atualizar_diario():
        conteudo_diario.controls.clear()
        usuario = estado_app["usuario"]
        conexao = conectar_banco()
        cursor = conexao.cursor()
        mes_atual = datetime.now().strftime("%Y-%m")
        
        cursor.execute(
            "SELECT data, mensagem FROM gratidao WHERE usuario = %s AND data LIKE %s ORDER BY data DESC", 
            (usuario, f"{mes_atual}-%")
        )
        registros = cursor.fetchall()
        conexao.close()
        
        lista_registros = ft.Column(spacing=10, width=450)
        
        if not registros:
            lista_registros.controls.append(
                ft.Text("Nenhuma gratidão registrada neste mês ainda.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
            )
            
        for data_str, msg in registros:
            data_br = datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            card = ft.Container(
                content=ft.Column([
                    ft.Text(data_br, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_ACCENT), 
                    ft.Text(msg)
                ]), 
                bgcolor=ft.Colors.GREY_900, 
                padding=15, 
                border_radius=10, 
                border=ft.Border.all(1, ft.Colors.GREY_800)
            )
            lista_registros.controls.append(card)
            
        btn_exportar = ft.FilledButton(
            "Baixar Diário do Mês", 
            icon=ft.Icons.DOWNLOAD, 
            bgcolor=ft.Colors.BLUE_600, 
            on_click=exportar_diario
        )
        
        conteudo_diario.controls.extend([
            ft.Divider(), 
            ft.Text("📖 Diário da Gratidão", size=24, weight=ft.FontWeight.BOLD), 
            ft.Text("Seus pensamentos do mês consolidado", size=14, color=ft.Colors.GREY_400), 
            ft.Container(height=10), 
            btn_exportar, 
            ft.Container(height=10), 
            lista_registros
        ])

    visual_atual = ft.Column(controls=[conteudo_checklist], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def alternar_para_checklist(e):
        visual_atual.controls = [conteudo_checklist]
        botao_menu_checklist.bgcolor = ft.Colors.GREEN_700
        botao_menu_dashboard.bgcolor = ft.Colors.GREY_800
        botao_menu_diario.bgcolor = ft.Colors.GREY_800
        page.update()

    def alternar_para_dashboard(e):
        estado_app["data_dashboard"] = datetime.now() 
        atualizar_dashboard() 
        visual_atual.controls = [conteudo_dashboard]
        botao_menu_checklist.bgcolor = ft.Colors.GREY_800
        botao_menu_dashboard.bgcolor = ft.Colors.GREEN_700
        botao_menu_diario.bgcolor = ft.Colors.GREY_800
        page.update()

    def alternar_para_diario(e):
        atualizar_diario()
        visual_atual.controls = [conteudo_diario]
        botao_menu_checklist.bgcolor = ft.Colors.GREY_800
        botao_menu_dashboard.bgcolor = ft.Colors.GREY_800
        botao_menu_diario.bgcolor = ft.Colors.GREEN_700
        page.update()

    botao_menu_checklist = ft.FilledButton(
        content=ft.Text("📋 Checklist", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_checklist, 
        bgcolor=ft.Colors.GREEN_700
    )
    
    botao_menu_dashboard = ft.FilledButton(
        content=ft.Text("🏆 Metas", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_dashboard, 
        bgcolor=ft.Colors.GREY_800
    )
    
    botao_menu_diario = ft.FilledButton(
        content=ft.Text("📖 Diário", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), 
        on_click=alternar_para_diario, 
        bgcolor=ft.Colors.GREY_800
    )
    
    linha_abas_custom = ft.Row(
        controls=[botao_menu_checklist, botao_menu_dashboard, botao_menu_diario], 
        alignment=ft.MainAxisAlignment.CENTER, 
        spacing=10
    )

    page.add(tela_login)

porta_nuvem = int(os.environ.get("PORT", 8080))
ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=porta_nuvem)
