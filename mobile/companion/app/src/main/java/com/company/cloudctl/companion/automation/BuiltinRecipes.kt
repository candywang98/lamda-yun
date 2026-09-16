package com.company.cloudctl.companion.automation

import org.json.JSONObject

object BuiltinRecipes {
    val OPEN_ONLY_COMMAND_TYPES = setOf(
        "xianyu.publish_listing.v1",
        "xiaohongshu.publish_note.v1",
    )

    fun packageJson(versionId: String): String? = PACKAGES[versionId]

    fun jsonFor(command: CommandV1): String {
        val encoded = packageJson(command.recipeVersionId)
            ?: error(CommandV1Parser.UNSUPPORTED_RECIPE)
        val root = JSONObject(encoded)
        val manifest = root.getJSONObject("manifest")
        require(manifest.getString("hash") == command.recipeSha256) { "recipe hash mismatch" }
        require(manifest.getString("app") == command.targetPackage) { "recipe app does not match command" }
        require(manifest.getJSONArray("commandTypes").getString(0) == command.commandType) {
            CommandV1Parser.UNSUPPORTED_RECIPE
        }
        return encoded
    }

    private val PACKAGES = mapOf(
        "recipe-device-probe-1" to """{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage","manifest":{"id":"recipe-device-probe-1","version":"1.0.0","hash":"901f795b2512891cd5ee08162626d0ad6a1c92ad9d7b922516c626f9d6f155b4","signingKeyId":"builtin-phase1","minEngineVersion":1,"platform":"companion","app":"com.company.cloudctl.companion","commandTypes":["device.probe_capabilities.v1"]},"graph":{"startStateId":"probe","maxIterations":8,"maxDurationMs":30000,"states":[{"stateId":"probe","action":"log","onSuccess":"SUCCEEDED","terminal":true}]},"signature":{"algorithm":"Ed25519","keyId":"builtin-phase1","digest":"hash-pinned-builtin"}}""",
        "recipe-xianyu-collect-1" to """{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage","manifest":{"id":"recipe-xianyu-collect-1","version":"1.0.0","hash":"d567f2b8ea3f338af9360c5befc7124770ae92d17e932cb7b03cd6e3f2d4b4b3","signingKeyId":"builtin-phase1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.collect_orders.v1"]},"graph":{"startStateId":"collect","maxIterations":8,"maxDurationMs":30000,"states":[{"stateId":"collect","action":"log","onSuccess":"SUCCEEDED","terminal":true}]},"signature":{"algorithm":"Ed25519","keyId":"builtin-phase1","digest":"hash-pinned-builtin"}}""",
        "recipe-xianyu-publish-1" to """{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage","manifest":{"id":"recipe-xianyu-publish-1","version":"1.0.0","hash":"a2331b8076dd28cd34f574f359b7e549ebef1f0ebd060bff2fad0ab410a84c0f","signingKeyId":"builtin-phase1","minEngineVersion":1,"platform":"xianyu","app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"]},"graph":{"startStateId":"open-only","maxIterations":8,"maxDurationMs":30000,"states":[{"stateId":"open-only","action":"checkpoint","onSuccess":"WAITING_USER","onPause":"WAITING_USER","terminal":true}]},"signature":{"algorithm":"Ed25519","keyId":"builtin-phase1","digest":"hash-pinned-builtin"}}""",
        "recipe-xianyu-publish-2" to """{"apiVersion":"cloudctl.recipe/v1","graph":{"maxDurationMs":600000,"maxIterations":40,"startStateId":"wait-home","states":[{"action":"wait","locatorRef":"xianyu_home_sell","onFailure":"FAILED","onSuccess":"open-sell","stateId":"wait-home"},{"action":"tap","locatorRef":"xianyu_home_sell","onFailure":"FAILED","onSuccess":"open-publish","postcondition":"xianyu_publish_entry","stateId":"open-sell"},{"action":"tap","locatorRef":"xianyu_publish_entry","onFailure":"FAILED","onSuccess":"await-form","postcondition":"xianyu_publish_page","stateId":"open-publish"},{"action":"wait","locatorRef":"xianyu_publish_page","onFailure":"FAILED","onSuccess":"select-media","stateId":"await-form"},{"action":"media","locatorRef":"xianyu_add_image","onFailure":"FAILED","onSuccess":"wait-edit-page","stateId":"select-media"},{"action":"wait","locatorRef":"xianyu_crop_done","onFailure":"FAILED","onSuccess":"confirm-crop","stateId":"wait-edit-page"},{"action":"tap","locatorRef":"xianyu_crop_done","onFailure":"FAILED","onSuccess":"await-form-back","stateId":"confirm-crop"},{"action":"wait","locatorRef":"xianyu_publish_page","onFailure":"FAILED","onSuccess":"fill-description","stateId":"await-form-back"},{"action":"input","locatorRef":"xianyu_description","onFailure":"FAILED","onSuccess":"capture-confirm-point","stateId":"fill-description","valueRef":"listingBody"},{"action":"extract","onFailure":"FAILED","onSuccess":"await-confirm","stateId":"capture-confirm-point"},{"action":"checkpoint","onPause":"WAITING_USER","onSuccess":"WAITING_USER","stateId":"await-confirm","terminal":true}]},"kind":"LocalRecipePackage","manifest":{"app":"com.taobao.idlefish","commandTypes":["xianyu.publish_listing.v1"],"hash":"f6adebdca3575cce16b64b62b6e27730de77868d64cceff3e83bee2223f62372","id":"recipe-xianyu-publish-2","minEngineVersion":1,"platform":"xianyu","signingKeyId":"builtin-phase1","version":"1.1.0"},"signature":{"algorithm":"Ed25519","digest":"hash-pinned-builtin","keyId":"builtin-phase1"}}""",
        "recipe-xhs-note-1" to """{"apiVersion":"cloudctl.recipe/v1","kind":"LocalRecipePackage","manifest":{"id":"recipe-xhs-note-1","version":"1.0.0","hash":"b1bdc6f334d2cea210c544183ff999244dfe4fe052b621d6aff6ddb9f495fda4","signingKeyId":"builtin-phase1","minEngineVersion":1,"platform":"xiaohongshu","app":"com.xingin.xhs","commandTypes":["xiaohongshu.publish_note.v1"]},"graph":{"startStateId":"open-only","maxIterations":8,"maxDurationMs":30000,"states":[{"stateId":"open-only","action":"checkpoint","onSuccess":"WAITING_USER","onPause":"WAITING_USER","terminal":true}]},"signature":{"algorithm":"Ed25519","keyId":"builtin-phase1","digest":"hash-pinned-builtin"}}""",
    )
}
