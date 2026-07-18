package com.nous.widgetmcp

class JsonRpcException(
    val rpcCode: Int,
    message: String,
    override val cause: Throwable? = null
) : Exception(message, cause)
