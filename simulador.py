import math
#simulador de file system indexado
BLOCK_SIZE = 4096  #4 KB
TOTAL_BLOCKS = 16  #64 KB total

class Inode:
    def __init__(self, is_dir):
        self.is_dir = is_dir
        self.size = 0
        self.data_blocks = [] # indices de blocos de dados

class FileNode:
    def __init__(self, name, is_dir, parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = {}
        self.inode_block = None  # i-node arquivo localizado / está guardado no disco
        self.inode = Inode(is_dir)

class FileSystem:
    def __init__(self):
        # disco na ram
        self.disk = ["[LIVRE]"] * TOTAL_BLOCKS
        
        # create root directory
        self.root = FileNode("/", is_dir=True)
        self.cwd = self.root
        
        # aloacao bloco 0 para o i-node do diretorio raiz
        self.root.inode_block = 0
        self.disk[0] = "[INODE_RAIZ]   : Diretório '/'"

    def _get_free_blocks(self, count):
        """Busca blocos livres no disco. Na alocação indexada, não precisam ser contíguos."""
        free_indices = [i for i, block in enumerate(self.disk) if block == "[LIVRE]"]
        if len(free_indices) < count:
            return None
        return free_indices[:count]

    def resolve_path(self, path):
        """Converte um caminho em string para o nó correspondente na árvore."""
        if path == "/": return self.root
        curr = self.root if path.startswith("/") else self.cwd
        parts = [p for p in path.split("/") if p not in ("", ".")]

        for p in parts:
            if p == "..":
                if curr.parent: curr = curr.parent
            elif p in curr.children:
                curr = curr.children[p]
            else:
                return None
        return curr

    def resolve_parent(self, path):
        """Retorna o diretório pai e o nome do novo arquivo/diretório a ser criado."""
        parts = path.rsplit("/", 1)
        if len(parts) == 1:
            return self.cwd, parts[0]
        parent_path = parts[0] if parts[0] != "" else "/"
        return self.resolve_path(parent_path), parts[1]

    def get_full_path(self, node):
        """Retorna o caminho absoluto de um nó."""
        if node == self.root: return "/"
        path = []
        while node != self.root:
            path.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(path))

    def mkdir(self, path):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir:
            print("Erro: Diretório pai não encontrado.")
            return
        if name in parent.children:
            print(f"Erro: O diretório '{name}' já existe.")
            return

        blocks = self._get_free_blocks(1) # necessita de 1 bloco para o i-node do diretório
        if not blocks:
            print("Erro: Disco cheio!")
            return

        new_dir = FileNode(name, is_dir=True, parent=parent)
        new_dir.inode_block = blocks[0]
        
        full_path = self.get_full_path(new_dir)
        self.disk[blocks[0]] = f"[INODE_DIR]    : Diretório '{full_path}'"
        parent.children[name] = new_dir
        print(f"Diretório '{full_path}' criado com sucesso.")

    def create(self, path, size_kb):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir:
            print("Erro: Diretório pai não encontrado.")
            return
        if name in parent.children:
            print(f"Erro: O arquivo '{name}' já existe.")
            return

        size_bytes = int(size_kb * 1024)
        data_blocks_needed = math.ceil(size_bytes / BLOCK_SIZE)
        total_blocks_needed = 1 + data_blocks_needed # um bloco pro i-node + N pros dados

        blocks = self._get_free_blocks(total_blocks_needed)
        if not blocks:
            print("Erro: Espaço insuficiente no disco para esta alocação.")
            return

        new_file = FileNode(name, is_dir=False, parent=parent)
        new_file.inode.size = size_bytes
        
        # separacao dos blocos alocados
        inode_block = blocks[0]
        data_blocks = blocks[1:]
        
        new_file.inode_block = inode_block
        new_file.inode.data_blocks = data_blocks
        
        full_path = self.get_full_path(new_file)
        
        # preenche o disc 
        nome_inode = name.upper().split(".")[0]
        self.disk[inode_block] = f"[INODE_{nome_inode[:3]}]    : Arquivo '{full_path}'"
        
        bytes_restantes = size_bytes
        for i, db in enumerate(data_blocks):
            ocupado = BLOCK_SIZE if bytes_restantes >= BLOCK_SIZE else bytes_restantes
            self.disk[db] = f"[DADO]         : '{full_path}' (Bloco {i+1} - {ocupado} bytes ocupados)"
            bytes_restantes -= ocupado

        parent.children[name] = new_file
        print(f"Arquivo '{full_path}' ({size_kb} KB) criado.")

    def rm(self, path):
        node = self.resolve_path(path)
        if not node or node == self.root:
            print("Erro: Arquivo ou diretório inválido.")
            return
        
        # Libera os blocos recursivamente
        def free_node(n):
            if n.inode_block is not None:
                self.disk[n.inode_block] = "[LIVRE]"
            for db in n.inode.data_blocks:
                self.disk[db] = "[LIVRE]"
            for child in n.children.values():
                free_node(child)

        free_node(node)
        del node.parent.children[node.name]
        print(f"'{path}' e todo o seu conteúdo foram deletados.")

    def tree(self, node=None, prefix=""):
        if node is None:
            node = self.root
            print("[ÁRVORE DO SISTEMA DE ARQUIVOS]")
            print("/")
            
        items = list(node.children.values())
        for i, child in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            if child.is_dir:
                print(f"{prefix}{connector}{child.name}/ [DIR]")
                self.tree(child, prefix + ("    " if is_last else "│   "))
            else:
                kb_size = child.inode.size / 1024
                print(f"{prefix}{connector}{child.name} ({kb_size:g} KB) [ARQ]")

    def fs_status(self):
        print(f"Tamanho do Bloco de Disco: {BLOCK_SIZE} B | Total de Blocos: {TOTAL_BLOCKS} ({TOTAL_BLOCKS * BLOCK_SIZE / 1024:g} KB)\n")
        print("[MAPA DE ALOCAÇÃO DO DISCO (Indexado)]")
        
        # agrupada visual de blocos livres
        livres_seq = []
        for i, block in enumerate(self.disk):
            if block == "[LIVRE]":
                livres_seq.append(i)
            else:
                if livres_seq:
                    print(f"Bloco {livres_seq[0]:02d}..{livres_seq[-1]:02d} : [LIVRE]")
                    livres_seq = []
                print(f"Bloco {i:02d} {block}")
        if livres_seq:
            print(f"Bloco {livres_seq[0]:02d}..{livres_seq[-1]:02d} : [LIVRE]")

        print("\n--- RELATÓRIO DE FRAGMENTAÇÃO ---")
        
        total_internal_frag = 0
        file_count = 0
        
        def calculate_frag(n):
            nonlocal total_internal_frag, file_count
            if not n.is_dir:
                file_count += 1
                if n.inode.size > 0:
                    espaco_alocado = len(n.inode.data_blocks) * BLOCK_SIZE
                    frag = espaco_alocado - n.inode.size
                    total_internal_frag += frag
                    if file_count == 1: # apenas para o primeiro arquivo, exibe detalhes
                        print(f"Tamanho Real do Arquivo '{n.name}': {n.inode.size} bytes")
                        print(f"Espaço Alocado no Disco          : {espaco_alocado} bytes ({len(n.inode.data_blocks)} blocos de {BLOCK_SIZE//1024} KB)")
                        pct = (frag / BLOCK_SIZE) * 100
                        print(f"Fragmentação Interna             : {frag} bytes ({pct:.0f}% de desperdício no último bloco)")
            for child in n.children.values():
                calculate_frag(child)
                
        calculate_frag(self.root)
        
        print(f"Fragmentação Externa             : 0 bytes (Inexistente na alocação Indexada)")
        print(f"Necessidade de Compactação       : NÃO (Blocos alocados via i-node indexado)")

# temrinal interativo
def start_shell():
    fs = FileSystem()
    print("Simulador de File System Iniciado. Digite 'help' para ver os comandos.")
    
    while True:
        try:
            cwd_path = fs.get_full_path(fs.cwd)
            prompt = f"fs@{cwd_path}> "
            cmd_input = input(prompt).strip()
            if not cmd_input: continue
            
            parts = cmd_input.split()
            cmd = parts[0].lower()
            
            if cmd == "exit" or cmd == "quit":
                break
            elif cmd == "help":
                print("Comandos suportados: mkdir <dir>, create <arq> --size <KB>, rm <path>, tree, fs_status --details, cd <dir>")
            elif cmd == "mkdir" and len(parts) == 2:
                fs.mkdir(parts[1])
            elif cmd == "create" and len(parts) == 4 and parts[2] == "--size":
                size = float(parts[3].upper().replace("KB", ""))
                fs.create(parts[1], size)
            elif cmd == "rm" and len(parts) == 2:
                fs.rm(parts[1])
            elif cmd == "tree":
                fs.tree()
            elif cmd == "fs_status" and "--details" in parts:
                fs.fs_status()
            elif cmd == "cd" and len(parts) == 2:
                node = fs.resolve_path(parts[1])
                if node and node.is_dir:
                    fs.cwd = node
                else:
                    print("Diretório não encontrado.")
            else:
                print("Comando inválido ou parâmetros incorretos.")
        except Exception as e:
            print(f"Erro inesperado: {e}")

if __name__ == "__main__":
    start_shell()