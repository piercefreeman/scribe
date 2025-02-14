from pathlib import Path
import subprocess
from typing import Optional
from unittest.mock import Mock, MagicMock

import pytest

from scribe.compile import (
    BuildResult,
    CompileHandler,
    DockerNodeBuilder,
    TSXCompileStrategy,
    CSSCompileStrategy,
    HTMLCompileStrategy,
    DockerRunner,
    FileSystem,
)
from scribe.metadata import CompileAsset, CompileAssetType


class MockDockerRunner:
    def __init__(self, should_fail: bool = False):
        self.build_image = Mock()
        self.run_container = Mock()
        self.should_fail = should_fail
        
        if should_fail:
            self.run_container.side_effect = subprocess.CalledProcessError(1, "docker run")


class MockFileSystem:
    def __init__(self, package_root: Optional[Path] = None):
        self.copy_tree = Mock()
        self.copy_file = Mock()
        self.ensure_directory = Mock()
        self.find_ancestor_with_file = Mock(return_value=package_root)
        self.files: dict[Path, bytes] = {}
    
    def add_file(self, path: Path, content: bytes = b""):
        self.files[path] = content


@pytest.fixture
def mock_docker():
    return MockDockerRunner()


@pytest.fixture
def mock_fs():
    return MockFileSystem(package_root=Path("/mock/project"))


def test_docker_node_builder_initialization(mock_docker, mock_fs):
    builder = DockerNodeBuilder(mock_docker, mock_fs)
    mock_docker.build_image.assert_called_once()
    assert mock_docker.build_image.call_args[0][1] == "scribe-node-builder:latest"


def test_docker_node_builder_successful_build(mock_docker, mock_fs):
    builder = DockerNodeBuilder(mock_docker, mock_fs)
    result = builder.build(
        "js",
        Path("/mock/project/src/component.tsx"),
        Path("/mock/output/component.js")
    )
    
    assert result.success
    assert result.output_path == Path("/mock/output/component.js")
    assert not result.error_message
    
    # Verify Docker was called correctly
    mock_docker.run_container.assert_called_once()
    call_args = mock_docker.run_container.call_args
    assert call_args[0][0] == "scribe-node-builder:latest"
    assert call_args[0][1] == ["js", "src/component.tsx", "component.js"]


def test_docker_node_builder_failed_build(mock_docker, mock_fs):
    mock_docker.should_fail = True
    builder = DockerNodeBuilder(mock_docker, mock_fs)
    result = builder.build(
        "js",
        Path("/mock/project/src/component.tsx"),
        Path("/mock/output/component.js")
    )
    
    assert not result.success
    assert result.error_message
    assert "docker run" in result.error_message


def test_tsx_compile_strategy(mock_docker, mock_fs):
    builder = DockerNodeBuilder(mock_docker, mock_fs)
    strategy = TSXCompileStrategy(builder)
    
    asset = CompileAsset(
        path="src/component.tsx",
        type=CompileAssetType.TSX,
        output_path="dist/component.js"
    )
    
    result = strategy.compile(
        asset,
        Path("/mock/source"),
        Path("/mock/output")
    )
    
    assert result.success
    mock_docker.run_container.assert_called_once()


def test_css_compile_strategy(mock_docker, mock_fs):
    builder = DockerNodeBuilder(mock_docker, mock_fs)
    strategy = CSSCompileStrategy(builder)
    
    asset = CompileAsset(
        path="src/styles.css",
        type=CompileAssetType.CSS,
        output_path="dist/styles.css"
    )
    
    result = strategy.compile(
        asset,
        Path("/mock/source"),
        Path("/mock/output")
    )
    
    assert result.success
    mock_docker.run_container.assert_called_once()


def test_html_compile_strategy(mock_fs):
    strategy = HTMLCompileStrategy(mock_fs)
    
    asset = CompileAsset(
        path="src/index.html",
        type=CompileAssetType.HTML,
        output_path="dist/index.html"
    )
    
    result = strategy.compile(
        asset,
        Path("/mock/source"),
        Path("/mock/output")
    )
    
    assert result.success
    mock_fs.copy_file.assert_called_once()


def test_compile_handler_unknown_type(mock_docker, mock_fs):
    handler = CompileHandler()
    
    # Create an asset with an unknown type
    class UnknownType(CompileAssetType):
        UNKNOWN = "unknown"
    
    asset = CompileAsset(
        path="src/unknown.xyz",
        type=UnknownType.UNKNOWN,
        output_path="dist/unknown.xyz"
    )
    
    result = handler.compile_asset(
        asset,
        Path("/mock/source"),
        Path("/mock/output")
    )
    
    assert not result.success
    assert "No compile strategy found" in result.error_message


def test_compile_handler_with_custom_strategies():
    mock_strategy = Mock()
    mock_strategy.compile.return_value = BuildResult(success=True)
    
    handler = CompileHandler({
        CompileAssetType.TSX: mock_strategy
    })
    
    asset = CompileAsset(
        path="src/component.tsx",
        type=CompileAssetType.TSX,
        output_path="dist/component.js"
    )
    
    result = handler.compile_asset(
        asset,
        Path("/mock/source"),
        Path("/mock/output")
    )
    
    assert result.success
    mock_strategy.compile.assert_called_once() 