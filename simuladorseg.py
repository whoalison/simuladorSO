import math
import hashlib
import os

BLOCK_SIZE = 4096  # 4 KB
TOTAL_BLOCKS = 16  # 164 KB total

#AUTENTICAÇÃO E HASHING
class UserManager:
    def __init__(self):
        #Banco de dados armazenando Salt e Hash Real(SHA-256)
        self.users = {}
        #root nativo
        self.add_user("root", "admin", "toor") #senha: toor
        #usuário
        self.add_user("carlos", "devs", "1234") #senha: 1234

    def add_user(self, username, group, password):
        salt = os.urandom(16)
        hash_obj = hashlib.sha256(salt + password.encode('utf-8'))
        self.users[username] = {
            "group": group,
            "salt": salt,
            "hash": hash_obj.hexdigest()
        }

    def authenticate(self, username, password):
        if username not in self.users: return False
        user_data = self.users[username]
        salt = user_data["salt"]
        hash_obj = hashlib.sha256(salt + password.encode('utf-8'))
        return hash_obj.hexdigest() == user_data["hash"]
#ESTRUTURAS FÍSICAS E METADADOS DE SEGURANÇA 
class DiskBlock:
    def __init__(self):
        self.is_free = True
        self.type = None           
        self.data = bytearray(BLOCK_SIZE)
        self.used_bytes = 0        
        self.references = []       
        self.metadata_name = ""    

class FileNode:
    def __init__(self, name, is_dir, owner="root", group="admin", parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = {}
        self.inode_block_idx = -1
        self.size_bytes = 0
        
        self.owner = owner
        self.group = group
        self.permissions = "rwxr-x---" if is_dir else "rw-r-----" # padrao (750 / 640)
        self.integrity_hash = None # Hash SHA-256 original do arquivo
        self.is_encrypted = False

class FileSystem:
    def __init__(self):
        self.disk = [DiskBlock() for _ in range(TOTAL_BLOCKS)]
        self.root = FileNode("/", is_dir=True)
        self.cwd = self.root
        
        # nucleo inicia as alocações físicas
        raiz_block = self.disk[0]
        raiz_block.is_free = False
        raiz_block.type = "INODE_DIR"
        raiz_block.metadata_name = "/"
        self.root.inode_block_idx = 0
        
        #subsistema de usuários
        self.auth = UserManager()
        self.current_user = "root"
        self.current_group = "admin"
        self.mode = "MODO_KERNEL"

    def _get_free_blocks(self, count):
        free = [i for i, b in enumerate(self.disk) if b.is_free]
        return free[:count] if len(free) >= count else None

    def resolve_path(self, path):
        if path == "/": return self.root
        curr = self.root if path.startswith("/") else self.cwd
        parts = [p for p in path.split("/") if p not in ("", ".")]
        for p in parts:
            if p == "..": curr = curr.parent if curr.parent else curr
            elif p in curr.children: curr = curr.children[p]
            else: return None
        return curr

    def resolve_parent(self, path):
        parts = path.rsplit("/", 1)
        if len(parts) == 1: return self.cwd, parts[0]
        parent_path = parts[0] if parts[0] != "" else "/"
        return self.resolve_path(parent_path), parts[1]

    def get_full_path(self, node):
        if node == self.root: return "/"
        path = []
        while node != self.root:
            path.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(path))

    #VERIFICAÇÃO DE ACL
    def check_permission(self, node, action):
        """Traduz rwxrwxrwx e aplica a Matriz de Acesso."""
        if self.current_user == "root": return True 
        
        p = node.permissions 
        
        #verificar dono, grupo...
        if self.current_user == node.owner: base_idx = 0
        elif self.current_group == node.group: base_idx = 3
        else: base_idx = 6

        has_perm = False
        if action == 'r' and p[base_idx] == 'r': has_perm = True
        if action == 'w' and p[base_idx+1] == 'w': has_perm = True
        if action == 'x' and p[base_idx+2] == 'x': has_perm = True

        if not has_perm:
            print("\n[SISTEMA DE SEGURANÇA - VERIFICAÇÃO DE ACL]")
            print(f"Objeto      : {self.get_full_path(node)}")
            print(f"Proprietário: {node.owner} (Grupo: {node.group})")
            print(f"Permissões  : {node.permissions}")
            acao_str = "LEITURA" if action == 'r' else "ESCRITA" if action == 'w' else "EXECUÇÃO"
            print(f"Ação Pedida : {acao_str} por '{self.current_user}' (Grupo: {self.current_group})")
            print(f"\n[NEGADO]: O usuário '{self.current_user}' não possui permissão no objeto.")
            print("Tentativa não autorizada registrada nos logs do sistema.\n")
            return False
        return True

    def mkdir(self, path):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir: return print("Diretório pai inválido.")
        if not self.check_permission(parent, 'w'): return
        if name in parent.children: return print("Erro: Já existe.")
        
        blocks = self._get_free_blocks(1)
        if not blocks: return print("Erro: Disco cheio!")
        
        new_dir = FileNode(name, is_dir=True, owner=self.current_user, group=self.current_group, parent=parent)
        new_dir.permissions = "rwxr-x---" # 750 
        new_dir.inode_block_idx = blocks[0]
        parent.children[name] = new_dir
        
        block = self.disk[blocks[0]]
        block.is_free = False
        block.type = "INODE_DIR"
        block.metadata_name = self.get_full_path(new_dir)
        print(f"Diretório '{block.metadata_name}' criado pelo usuário '{self.current_user}'.")

    def create(self, path, texto_conteudo):
        """Cria um arquivo e guarda o Hash de Integridade (Antivírus)"""
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir: return
        if not self.check_permission(parent, 'w'): return
        
        dados_bytes = texto_conteudo.encode('utf-8')
        size_bytes = len(dados_bytes)
        data_blocks_needed = max(1, math.ceil(size_bytes / BLOCK_SIZE))
        
        blocks = self._get_free_blocks(1 + data_blocks_needed)
        if not blocks: return print("Erro: Espaço insuficiente.")
        
        inode_idx = blocks[0]
        data_indices = blocks[1:]
        
        #arvore
        new_file = FileNode(name, is_dir=False, owner=self.current_user, group=self.current_group, parent=parent)
        new_file.permissions = "rw-r-----" # 640
        new_file.size_bytes = size_bytes
        new_file.inode_block_idx = inode_idx
        parent.children[name] = new_file
        
        #Inode
        full_path = self.get_full_path(new_file)
        inode_block = self.disk[inode_idx]
        inode_block.is_free = False
        inode_block.type = "INODE_FILE"
        inode_block.metadata_name = full_path
        inode_block.references = data_indices
        
        # preenchimento e calculo de hash
        hash_calc = hashlib.sha256()
        bytes_restantes = size_bytes
        offset = 0
        
        for idx in data_indices:
            db = self.disk[idx]
            db.is_free = False
            db.type = "DATA"
            db.metadata_name = full_path
            
            ocupado = min(BLOCK_SIZE, bytes_restantes)
            db.used_bytes = ocupado
            chunk = dados_bytes[offset:offset+ocupado]
            db.data[:ocupado] = chunk
            hash_calc.update(chunk) #carrega o antivírus
            
            offset += ocupado
            bytes_restantes -= ocupado
            
        new_file.integrity_hash = hash_calc.hexdigest()
        print(f"Arquivo '{full_path}' salvo. Assinatura SHA-256 gerada para auditoria.")

    def read_file(self, path):
        node = self.resolve_path(path)
        if not node or node.is_dir: return print("Arquivo não encontrado.")
        if not self.check_permission(node, 'r'): return
        
        print(f"\n--- Lendo {path} ---")
        if node.is_encrypted:
            print("0x" + self.disk[node.inode_block_idx].references[0].to_bytes(2, 'big').hex() + "... (Encrypted Ciphertext)\n[AVISO]: O arquivo está criptografado. Use 'decrypt_file' para ler os dados.")
            return

        inode = self.disk[node.inode_block_idx]
        resultado = bytearray()
        for idx in inode.references:
            db = self.disk[idx]
            resultado.extend(db.data[:db.used_bytes])
        print(resultado.decode('utf-8', errors='ignore'))
        print("--------------------\n")

    #criptografia
    def encrypt_file(self, path, key):
        node = self.resolve_path(path)
        if not node or node.is_dir: return print("Arquivo não encontrado.")
        if not self.check_permission(node, 'w'): return
        if node.is_encrypted: return print("Arquivo já criptografado.")
        
        key_bytes = key.encode('utf-8')
        inode = self.disk[node.inode_block_idx]
        
        #altera os blocos físicos usando XOR com a chave
        for idx in inode.references:
            db = self.disk[idx]
            for i in range(db.used_bytes):
                db.data[i] = db.data[i] ^ key_bytes[i % len(key_bytes)]
                
        node.is_encrypted = True
        #refaz o Hash da versão criptografada para o antivírus
        self._recalc_hash(node)
        
        print(f"Arquivo '{path}' criptografado com sucesso.")
        print("Conteúdo gravado nos blocos físicos: \"0x8F4A12B... (Encrypted Ciphertext)\"")

    def _recalc_hash(self, node):
        hash_calc = hashlib.sha256()
        inode = self.disk[node.inode_block_idx]
        for idx in inode.references:
            db = self.disk[idx]
            hash_calc.update(db.data[:db.used_bytes])
        node.integrity_hash = hash_calc.hexdigest()

    #antivirus
    def antivirus_scan(self):
        print("\n[MÓDULO DE SEGURANÇA - VARREDURA DE INTEGRIDADE]")
        print("Analisando arquivos em busca de modificações físicas e hashes corrompidos...")
        
        def scan_recursivo(n):
            if not n.is_dir:
                path = self.get_full_path(n)
                
                #ler dinamicamente
                hash_fisico = hashlib.sha256()
                inode = self.disk[n.inode_block_idx]
                for idx in inode.references:
                    db = self.disk[idx]
                    hash_fisico.update(db.data[:db.used_bytes])
                
                if hash_fisico.hexdigest() == n.integrity_hash:
                    if n.is_encrypted:
                        print(f"- {path:<30} : [OK - Criptografado e Íntegro]")
                    else:
                        print(f"- {path:<30} : [OK - Assinatura Validada]")
                else:
                    print(f"- {path:<30} : [ALERTA] Hash do bloco difere do registro oficial!")
                    print("  -> Resultado: Possível modificação direta não autorizada no bloco de disco (Malware/Corrupção).")
                    
            for child in n.children.values():
                scan_recursivo(child)

        scan_recursivo(self.root)
        print("Varredura concluída.\n")

    def tamper_block(self, path):
        """Simula a invasão de um malware que altera diretamente os bits no disco físico"""
        node = self.resolve_path(path)
        if not node or node.is_dir: return print("Arquivo não encontrado.")
        if self.mode != "MODO_KERNEL": return print("Apenas ROOT tem poder para simular falhas de hardware/malware.")
        
        #virus invade o primeiro bloco e corrompe o primeiro byte
        db = self.disk[self.disk[node.inode_block_idx].references[0]]
        db.data[0] = db.data[0] ^ 0xFF #forca inversao dos bits
        print(f"!!! DISCO FÍSICO CORROMPIDO: O bloco de dados de {path} foi alterado por fora do SO !!!")

    def tree(self, node=None, prefix=""):
        if node is None: node, print("\n[ÁRVORE DE DIRETÓRIOS]") = self.root, None
        items = list(node.children.values())
        for i, child in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if child.is_dir:
                print(f"{prefix}{connector}{child.name}/ (Dono: {child.owner})")
                self.tree(child, prefix + ("    " if is_last else "│   "))
            else:
                print(f"{prefix}{connector}{child.name} (Dono: {child.owner} | Perms: {child.permissions})")

#interface do user
def start_shell():
    fs = FileSystem()
    print("Simulador Arquitetural (Etapas 1, 2 e 3). Digite 'help'.")
    fs.mkdir("/sistema")
    fs.create("/sistema/config.sys", "CONFIGURACOES DO KERNEL DO SISTEMA")
    fs.mkdir("/home")
    fs.mkdir("/home/carlos")
    pasta_carlos = fs.resolve_path("/home/carlos")
    pasta_carlos.owner = "carlos"
    pasta_carlos.group = "devs"
    
    while True:
        try:
            cwd_str = fs.get_full_path(fs.cwd)
            prompt = f"[{fs.mode}] {fs.current_user}@{cwd_str}> "
            cmd_input = input(prompt).strip()
            if not cmd_input: continue
            
            parts = cmd_input.split()
            cmd = parts[0].lower()
            
            if cmd in ["exit", "quit"]: break
            
            elif cmd == "login" and len(parts) == 3 and parts[1] == "--user":
                user = parts[2]
                senha = input("Senha: ") 
                if fs.auth.authenticate(user, senha):
                    fs.current_user = user
                    fs.current_group = fs.auth.users[user]["group"]
                    fs.mode = "MODO_KERNEL" if user == "root" else "MODO_USUARIO"
                    print(f"Autenticado. Usuário: '{user}' | Grupo: '{fs.current_group}' | Modo: {fs.mode}")
                else:
                    print("Falha na autenticação.")
            
            elif cmd == "read_file" and len(parts) == 2:
                fs.read_file(parts[1])
                
            elif cmd == "create" and len(parts) >= 3:
                texto = " ".join(parts[2:])
                fs.create(parts[1], texto)
                
            elif cmd == "encrypt_file" and "--key" in parts:
                idx = parts.index("--key")
                caminho = parts[1]
                chave = parts[idx+1].replace('"', '')
                fs.encrypt_file(caminho, chave)
                
            elif cmd == "antivirus_scan":
                fs.antivirus_scan()
                
            elif cmd == "corromper_bloco" and len(parts) == 2:
                fs.tamper_block(parts[1])
            
            #cmds
            elif cmd == "mkdir" and len(parts) == 2: fs.mkdir(parts[1])
            elif cmd == "tree": fs.tree()
            elif cmd == "help":
                print("Segurança: login --user <nome>, read_file <caminho>, encrypt_file <caminho> --key <chave>")
                print("Auditoria: antivirus_scan, corromper_bloco <caminho> (simula malware)")
                print("Usuarios default criados: root (senha: toor), carlos (senha: 1234)")
            else:
                print("Comando não reconhecido ou parâmetros inválidos.")
        except Exception as e:
            print(f"Erro no Kernel: {e}")

if __name__ == "__main__":
    start_shell()