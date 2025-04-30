import ast
import logging
import copy

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def clean_ast(node):
    """Recursively remove None nodes from the AST."""
    if node is None:
        return None
    if isinstance(node, list):
        return [clean_ast(n) for n in node if n is not None]
    if not isinstance(node, ast.AST):
        return node

    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(node, field, [n for n in clean_ast(value) if n is not None])
        elif value is not None:
            setattr(node, field, clean_ast(value))
    return node

class VariableCollector(ast.NodeVisitor):
    """Collect all variables used in the code (Load contexts and Store with dependencies)."""
    def __init__(self):
        self.used_vars = set()
        self.dependencies = {}

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used_vars.add(node.id)
        self.generic_visit(node)

    def visit_Assign(self, node):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            # Mark variable as used if its value references another variable
            if isinstance(node.value, ast.Name):
                self.used_vars.add(target)
                self.dependencies[target] = node.value.id
            # Mark variables assigned constants as used if they appear in Load contexts
            elif isinstance(node.value, ast.Num) and target in self.used_vars:
                self.dependencies[target] = 'constant'
        self.generic_visit(node)

class Optimizer(ast.NodeTransformer):
    def __init__(self, used_vars):
        # Track variable usage for dead code elimination
        self.used_vars = used_vars
        # Track constant variable assignments for propagation
        self.const_vars = {}
        # Track loop-invariant statements for the current pass
        self.invariants = []
        # Track all invariants across passes
        self.persistent_invariants = []

    def visit_Assign(self, node):
        # Handle redundant assignments (e.g., x = x)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Name) and node.targets[0].id == node.value.id:
                logger.debug(f"Removing redundant assignment: {node.targets[0].id}")
                return None

        # Visit value to propagate constants
        node.value = self.visit(node.value)

        # Variable propagation: Replace variable with constant if known
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Name) and node.value.id in self.const_vars:
                logger.debug(f"Propagating constant in assignment: {node.value.id} -> {self.const_vars[node.value.id]}")
                node.value = ast.Num(n=self.const_vars[node.value.id])
                self.const_vars[node.targets[0].id] = node.value.n
                self.used_vars.add(node.targets[0].id)  # Preserve propagated variables
            elif isinstance(node.value, ast.Num):
                self.const_vars[node.targets[0].id] = node.value.n
                logger.debug(f"Registered constant: {node.targets[0].id} = {node.value.n}")

        return node

    def visit_BinOp(self, node):
        # Log initial BinOp structure
        logger.debug(f"Processing BinOp: {ast.dump(node, indent=2)}")

        # Visit children to propagate constants
        node.left = self.visit(node.left)
        node.right = self.visit(node.right)

        # Propagate constants in BinOp
        if isinstance(node.left, ast.Name) and node.left.id in self.const_vars:
            logger.debug(f"Propagating constant in BinOp: {node.left.id} -> {self.const_vars[node.left.id]}")
            node.left = ast.Num(n=self.const_vars[node.left.id])
        if isinstance(node.right, ast.Name) and node.right.id in self.const_vars:
            logger.debug(f"Propagating constant in BinOp: {node.right.id} -> {self.const_vars[node.right.id]}")
            node.right = ast.Num(n=self.const_vars[node.right.id])

        # Constant folding (e.g., 2 + 3 -> 5)
        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            if isinstance(node.left, ast.Num) and isinstance(node.right, ast.Num):
                if isinstance(node.op, ast.Add):
                    logger.debug(f"Folding {node.left.n} + {node.right.n}")
                    return ast.Num(n=node.left.n + node.right.n)
                elif isinstance(node.op, ast.Mult):
                    logger.debug(f"Folding {node.left.n} * {node.right.n}")
                    return ast.Num(n=node.left.n * node.right.n)
            # Re-visit entire node if either side is a BinOp
            if isinstance(node.left, ast.BinOp) or isinstance(node.right, ast.BinOp):
                node.left = self.visit(node.left)
                node.right = self.visit(node.right)
            else:
                break
            iteration += 1

        logger.debug(f"BinOp after processing: {ast.dump(node, indent=2)}")
        return node

    def visit_For(self, node):
        # Loop-invariant code motion: Collect constant assignments
        new_body = []
        self.invariants = []  # Reset invariants for this loop in the current pass

        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Num):
                    logger.debug(f"Found loop-invariant: {target.id} = {stmt.value.n}")
                    self.invariants.append(copy.deepcopy(stmt))  # Deep copy for current pass
                    self.persistent_invariants.append(copy.deepcopy(stmt))  # Store in persistent list
                    # Update const_vars and used_vars immediately
                    self.const_vars[target.id] = stmt.value.n
                    self.used_vars.add(target.id)
                    logger.debug(f"Registered constant from invariant: {target.id} = {stmt.value.n}")
                    continue
            visited_stmt = self.visit(stmt)
            if visited_stmt is not None:
                new_body.append(visited_stmt)

        node.body = new_body
        return node

    def visit_Expr(self, node):
        # Variable propagation: Replace variable with constant if known
        node.value = self.visit(node.value)
        if isinstance(node.value, ast.Name) and node.value.id in self.const_vars:
            logger.debug(f"Propagating constant: {node.value.id} -> {self.const_vars[node.value.id]}")
            return ast.Expr(value=ast.Num(n=self.const_vars[node.value.id]))
        return node

    def visit_Name(self, node):
        # Propagate constants in Name nodes
        if isinstance(node.ctx, ast.Load) and node.id in self.const_vars:
            logger.debug(f"Propagating constant in Name: {node.id} -> {self.const_vars[node.id]}")
            return ast.Num(n=self.const_vars[node.id])
        return node

def optimize_python_code(code: str) -> str:
    try:
        # Parse code to AST
        tree = ast.parse(code)
        logger.debug("Initial AST:\n" + ast.dump(tree, indent=2))

        # Collect all used variables
        collector = VariableCollector()
        collector.visit(tree)
        used_vars = collector.used_vars
        logger.debug(f"Used variables: {used_vars}")
        logger.debug(f"Dependencies: {collector.dependencies}")

        optimizer = Optimizer(used_vars)

        # Multiple passes to ensure all optimizations are applied
        max_passes = 3
        for pass_num in range(max_passes):
            logger.debug(f"Optimization pass {pass_num + 1}")
            logger.debug(f"const_vars before pass {pass_num + 1}: {optimizer.const_vars}")
            logger.debug(f"used_vars before pass {pass_num + 1}: {optimizer.used_vars}")
            logger.debug(f"persistent_invariants before pass {pass_num + 1}: {[ast.unparse(inv) for inv in optimizer.persistent_invariants]}")
            tree = optimizer.visit(tree)
            tree = clean_ast(tree)
            if tree is None:
                return "Error: AST became empty during optimization pass"
            logger.debug(f"AST after pass {pass_num + 1}:\n" + ast.dump(tree, indent=2))
            logger.debug(f"persistent_invariants after pass {pass_num + 1}: {[ast.unparse(inv) for inv in optimizer.persistent_invariants]}")

        # Insert loop-invariant assignments
        if isinstance(tree, ast.Module):
            logger.debug(f"Persistent invariants before insertion: {[ast.unparse(inv) for inv in optimizer.persistent_invariants]}")
            if optimizer.persistent_invariants:
                # Insert invariants after non-loop statements
                invariants = [copy.deepcopy(inv) for inv in optimizer.persistent_invariants if inv is not None]
                new_body = []
                inserted = False
                for node in tree.body:
                    if isinstance(node, ast.For) and not inserted:
                        new_body.extend(invariants)
                        inserted = True
                    new_body.append(node)
                if not inserted:
                    new_body.extend(invariants)
                tree.body = new_body
                logger.debug(f"Inserted invariants: {[ast.unparse(inv) for inv in invariants]}")
                logger.debug(f"AST after invariant insertion:\n" + ast.dump(tree, indent=2))
                logger.debug(f"Module body after invariant insertion: {[ast.unparse(n) for n in tree.body]}")
            optimizer.persistent_invariants = []  # Clear after insertion

        # Second pass: Remove dead code
        class DeadCodeEliminator(ast.NodeTransformer):
            def visit_Module(self, node):
                new_body = []
                logger.debug("Module body before dead code elimination: %s", [ast.unparse(n) for n in node.body])
                for stmt in node.body:
                    transformed_stmt = self.visit(stmt)
                    if transformed_stmt is not None:
                        new_body.append(transformed_stmt)
                node.body = new_body
                logger.debug("Module body after dead code elimination: %s", [ast.unparse(n) for n in node.body])
                return node

            def visit_Assign(self, node):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if node.targets[0].id not in optimizer.used_vars:
                        logger.debug(f"Removing dead code: {node.targets[0].id}")
                        return None
                return node

        logger.debug("AST before dead code elimination:\n" + ast.dump(tree, indent=2))
        tree = DeadCodeEliminator().visit(tree)
        logger.debug("AST after dead code elimination:\n" + ast.dump(tree, indent=2))

        # Clean AST again
        tree = clean_ast(tree)
        if tree is None:
            return "Error: AST became empty after dead code elimination"

        # Final clean and validation
        tree = clean_ast(tree)
        if tree is None:
            return "Error: AST became empty after final pass"
        ast.fix_missing_locations(tree)
        logger.debug("Final AST:\n" + ast.dump(tree, indent=2))

        # Convert back to code
        optimized_code = ast.unparse(tree).strip()
        return optimized_code
    except SyntaxError:
        return "Error: Invalid Python code"
    except Exception as e:
        logger.error(f"Optimization error: {str(e)}")
        return f"Error: Optimization failed - {str(e)}"