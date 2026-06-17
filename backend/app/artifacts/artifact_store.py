import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.artifacts.schemas import ArtifactContent
from app.core.config import Settings, get_settings
from app.core.models import Artifact


class ArtifactStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.artifact_path
        self.root.mkdir(parents=True, exist_ok=True)

    def save_text(
        self,
        *,
        run_id: str,
        name: str,
        artifact_type: str,
        content: str,
        agent_name: str,
        summary: str,
    ) -> Artifact:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact = Artifact(
            id=str(uuid.uuid4()),
            run_id=run_id,
            name=name,
            type=artifact_type,
            path=str(run_dir / name),
            created_at=datetime.now(UTC).isoformat(),
            agent_name=agent_name,
            summary=summary,
        )
        Path(artifact.path).write_text(content, encoding="utf-8")
        self._write_manifest(run_id, [*self.list_artifacts(run_id), artifact])
        return artifact

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        manifest = self._manifest_path(run_id)
        if not manifest.exists():
            return []
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return [Artifact.model_validate(item) for item in data]

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactContent:
        artifacts = self.list_artifacts(run_id)
        for artifact in artifacts:
            if artifact.id == artifact_id:
                path = Path(artifact.path)
                if not path.exists():
                    raise HTTPException(status_code=404, detail="Artifact file is missing.")
                return ArtifactContent(**artifact.model_dump(), content=path.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="Artifact not found.")

    def _manifest_path(self, run_id: str) -> Path:
        return self.root / run_id / "manifest.json"

    def _write_manifest(self, run_id: str, artifacts: list[Artifact]) -> None:
        manifest = self._manifest_path(run_id)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps([artifact.model_dump() for artifact in artifacts], indent=2),
            encoding="utf-8",
        )
