# import shutil
# import subprocess
# import tempfile
# from dataclasses import dataclass
# from pathlib import Path
# from typing import Optional, Protocol

# from scribe.metadata import CompileAsset, CompileAssetType


# @dataclass
# class BuildResult:
#     """
#     Result of a build operation
#     """

#     success: bool
#     output_path: Optional[Path] = None
#     error_message: Optional[str] = None
#     sourcemap_path: Optional[Path] = None


# class DockerRunner(Protocol):
#     """
#     Protocol for running Docker commands
#     """

#     def build_image(self, dockerfile_path: Path, tag: str) -> None: ...

#     def run_container(
#         self,
#         image: str,
#         command: list[str],
#         volumes: dict[Path, Path],
#     ) -> subprocess.CompletedProcess: ...


# class DefaultDockerRunner:
#     """
#     Default implementation of DockerRunner using subprocess
#     """

#     def build_image(self, dockerfile_path: Path, tag: str) -> None:
#         subprocess.run(["docker", "build", "-t", tag, str(dockerfile_path.parent)], check=True)

#     def run_container(
#         self,
#         image: str,
#         command: list[str],
#         volumes: dict[Path, Path],
#     ) -> subprocess.CompletedProcess:
#         volume_args = []
#         for host_path, container_path in volumes.items():
#             volume_args.extend(["-v", f"{host_path}:{container_path}"])

#         return subprocess.run(["docker", "run", "--rm", *volume_args, image, *command], check=True)


# class FileSystem(Protocol):
#     """
#     Protocol for file system operations
#     """

#     def copy_tree(self, src: Path, dst: Path, ignore_patterns: tuple[str, ...] = ()) -> None: ...

#     def copy_file(self, src: Path, dst: Path) -> None: ...

#     def ensure_directory(self, path: Path) -> None: ...

#     def find_ancestor_with_file(self, start_path: Path, filename: str) -> Optional[Path]: ...


# class DefaultFileSystem:
#     """
#     Default implementation of FileSystem using standard library
#     """

#     def copy_tree(self, src: Path, dst: Path, ignore_patterns: tuple[str, ...] = ()) -> None:
#         shutil.copytree(
#             src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*ignore_patterns)
#         )

#     def copy_file(self, src: Path, dst: Path) -> None:
#         shutil.copy2(src, dst)

#     def ensure_directory(self, path: Path) -> None:
#         path.mkdir(parents=True, exist_ok=True)

#     def find_ancestor_with_file(self, start_path: Path, filename: str) -> Optional[Path]:
#         current = start_path
#         while current.name:
#             if (current / filename).exists():
#                 return current
#             current = current.parent
#         return None


# class DockerNodeBuilder:
#     """
#     Handles building assets using the Node Docker builder
#     """

#     def __init__(
#         self,
#         docker_runner: DockerRunner = DefaultDockerRunner(),
#         file_system: FileSystem = DefaultFileSystem(),
#     ):
#         self.builder_path = Path(__file__).parent.parent / "builders" / "node"
#         self.image_name = "scribe-node-builder:latest"
#         self.docker = docker_runner
#         self.fs = file_system
#         self._ensure_builder()

#     def _ensure_builder(self) -> None:
#         """
#         Ensure the Docker image is built
#         """
#         self.docker.build_image(self.builder_path / "Dockerfile", self.image_name)

#     def build(self, build_type: str, input_path: Path, output_path: Path) -> BuildResult:
#         """
#         Build an asset using the Docker builder
#         """
#         try:
#             with tempfile.TemporaryDirectory() as temp_dir:
#                 temp_path = Path(temp_dir)

#                 # Find project root (with package.json) or use immediate parent
#                 source_root = (
#                     self.fs.find_ancestor_with_file(input_path.parent, "package.json")
#                     or input_path.parent
#                 )

#                 # Create relative paths for input/output
#                 rel_input = input_path.relative_to(source_root)
#                 rel_output = output_path.name

#                 # Copy the source directory to temp
#                 self.fs.copy_tree(source_root, temp_path, ignore_patterns=("node_modules", ".git"))

#                 # Run the builder
#                 self.docker.run_container(
#                     self.image_name,
#                     [build_type, str(rel_input), str(rel_output)],
#                     {temp_path: Path("/build")},
#                 )

#                 # Copy output back
#                 temp_output = temp_path / rel_output
#                 self.fs.ensure_directory(output_path.parent)

#                 result = BuildResult(success=True, output_path=output_path)

#                 if temp_output.exists():
#                     self.fs.copy_file(temp_output, output_path)

#                     # Copy sourcemap if it exists (for js builds)
#                     if build_type == "js":
#                         sourcemap = temp_output.with_suffix(temp_output.suffix + ".map")
#                         if sourcemap.exists():
#                             sourcemap_output = output_path.with_suffix(output_path.suffix + ".map")
#                             self.fs.copy_file(sourcemap, sourcemap_output)
#                             result.sourcemap_path = sourcemap_output

#                 return result

#         except Exception as e:
#             return BuildResult(success=False, error_message=str(e))


# class CompileStrategy(Protocol):
#     """
#     Protocol for compile strategies that handle different asset types
#     """

#     def compile(self, asset: CompileAsset, source_dir: Path, output_dir: Path) -> BuildResult: ...


# class TSXCompileStrategy:
#     def __init__(self, builder: Optional[DockerNodeBuilder] = None):
#         self.builder = builder or DockerNodeBuilder()

#     def compile(self, asset: CompileAsset, source_dir: Path, output_dir: Path) -> BuildResult:
#         """
#         Compile TSX files using esbuild in Docker
#         """
#         input_path = source_dir / asset.path
#         output_path = output_dir / asset.output_path
#         return self.builder.build("js", input_path, output_path)


# class CSSCompileStrategy:
#     def __init__(self, builder: Optional[DockerNodeBuilder] = None):
#         self.builder = builder or DockerNodeBuilder()

#     def compile(self, asset: CompileAsset, source_dir: Path, output_dir: Path) -> BuildResult:
#         """
#         Compile CSS files using postcss in Docker
#         """
#         input_path = source_dir / asset.path
#         output_path = output_dir / asset.output_path
#         return self.builder.build("css", input_path, output_path)


# class HTMLCompileStrategy:
#     def __init__(self, file_system: FileSystem = DefaultFileSystem()):
#         self.fs = file_system

#     def compile(self, asset: CompileAsset, source_dir: Path, output_dir: Path) -> BuildResult:
#         """
#         Copy HTML files directly
#         """
#         try:
#             input_path = source_dir / asset.path
#             output_path = output_dir / asset.output_path

#             self.fs.ensure_directory(output_path.parent)
#             self.fs.copy_file(input_path, output_path)

#             return BuildResult(success=True, output_path=output_path)
#         except Exception as e:
#             return BuildResult(success=False, error_message=str(e))


# class CompileHandler:
#     """
#     Handles the compilation of different asset types
#     """

#     def __init__(self, strategies: Optional[dict[CompileAssetType, CompileStrategy]] = None):
#         self.strategies = strategies or {
#             CompileAssetType.TSX: TSXCompileStrategy(),
#             CompileAssetType.CSS: CSSCompileStrategy(),
#             CompileAssetType.HTML: HTMLCompileStrategy(),
#         }

#     def compile_asset(self, asset: CompileAsset, source_dir: Path, output_dir: Path) -> BuildResult:
#         """
#         Compile a single asset using the appropriate strategy
#         """
#         strategy = self.strategies.get(asset.type)
#         if not strategy:
#             return BuildResult(
#                 success=False,
#                 error_message=f"No compile strategy found for asset type: {asset.type}",
#             )

#         return strategy.compile(asset, source_dir, output_dir)
