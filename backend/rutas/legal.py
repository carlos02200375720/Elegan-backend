from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.rutas.autenticacion import obtener_db, usuario_actual_admin

router_movil_legal = APIRouter(prefix="/api/movil/legal-documents", tags=["Documentos legales móvil"])
router_admin_legal = APIRouter(prefix="/api/admin/legal-documents", tags=["Documentos legales administrativos"])

TIPOS = ("privacy_policy", "terms_and_conditions")
DOCUMENTOS_INICIALES = {
    "privacy_policy": {
        "type": "privacy_policy",
        "title": "Política de Privacidad",
        "subtitle": "ELEGAN Boutique • República Dominicana",
        "content": "ELEGAN Boutique utiliza los datos personales necesarios para crear y administrar tu cuenta, procesar pedidos, coordinar entregas y ofrecer soporte.\n\nLos datos pueden incluir nombre, correo electrónico, teléfono y dirección de entrega. Los comprobantes y archivos que envíes se procesan para gestionar tu pedido o conversación.\n\nLa infraestructura tecnológica incluye Google Cloud y MongoDB Atlas. No vendemos tus datos personales.\n\nPuedes solicitar la eliminación de tu cuenta desde la aplicación o escribiendo a cg0220037@gmail.com. Los registros que deban conservarse por obligaciones legales se desvincularán de tu cuenta cuando corresponda.\n\nContacto: cg0220037@gmail.com.",
    },
    "terms_and_conditions": {
        "type": "terms_and_conditions",
        "title": "Términos y Condiciones de Uso",
        "subtitle": "Reglas de compra, contenido y convivencia",
        "content": "ELEGAN Boutique es una tienda de moda y accesorios masculinos operada en República Dominicana. La aplicación permite realizar compras y publicar comentarios visibles en las fichas de productos.\n\nLos usuarios son responsables del contenido que publican. No se permite contenido ilegal, amenazante, discriminatorio, acosador, engañoso, que infrinja derechos de terceros o que revele datos personales de otras personas.\n\nPuedes reportar comentarios que infrinjan estas reglas y bloquear a otros usuarios desde la aplicación. Los reportes serán revisados y podremos retirar contenido o restringir cuentas cuando corresponda.\n\nLos pedidos pagados mediante transferencia quedan pendientes hasta verificar el comprobante y confirmar la acreditación de los fondos.\n\nELEGAN puede rechazar comprobantes ilegibles, alterados o que no correspondan al importe del pedido.\n\nLas entregas en Santo Domingo se estiman en 24 a 48 horas hábiles y al interior en 2 a 4 días hábiles tras confirmar el pedido. Para soporte: cg0220037@gmail.com.",
    },
}


class DocumentoLegalEntrada(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    subtitle: str = Field(default="", max_length=240)
    content: str = Field(min_length=20, max_length=30000)


def _documento_publico(doc: dict) -> dict:
    return {
        "type": str(doc.get("type", "")),
        "title": str(doc.get("title", "")),
        "subtitle": str(doc.get("subtitle", "")),
        "content": str(doc.get("content", "")),
        "updatedAt": doc.get("updatedAt"),
    }


def _obtener_documentos(db):
    resultado = []
    for tipo in TIPOS:
        documento = db["legal_documents"].find_one({"_id": tipo})
        resultado.append(_documento_publico(documento or DOCUMENTOS_INICIALES[tipo]))
    return {"items": resultado}


@router_movil_legal.get("")
def documentos_moviles(db=Depends(obtener_db)):
    return _obtener_documentos(db)


@router_admin_legal.get("")
def documentos_admin(
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    return _obtener_documentos(db)


@router_admin_legal.put("/{doc_type}")
def guardar_documento(
    doc_type: Literal["privacy_policy", "terms_and_conditions"],
    datos: DocumentoLegalEntrada,
    _admin=Depends(usuario_actual_admin),
    db=Depends(obtener_db),
):
    ahora = datetime.now(timezone.utc)
    documento = {
        "_id": doc_type,
        "type": doc_type,
        "title": datos.title.strip(),
        "subtitle": datos.subtitle.strip(),
        "content": datos.content.strip(),
        "updatedAt": ahora,
    }
    db["legal_documents"].replace_one({"_id": doc_type}, documento, upsert=True)
    return {"success": True, "item": _documento_publico(documento)}
